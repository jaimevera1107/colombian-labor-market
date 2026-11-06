"""Donor selection for the nine cities without GEIH history (2007-2020).

A recipient city borrows the *trajectory* of a donor city with history,
rescaled to its own level: ``y_r(t) = alpha * y_d(t)``, where ``alpha`` is
calibrated on the selection years of the window proxies. Donors are chosen
by a five-criterion Pareto analysis (all criteria are losses), a weighted
regret tie-break, and two guards relative to the incumbent donor: the
holdout-year error and the seam (first proxy year) continuity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.urban.inputs import UrbanSources

FEATURES: tuple[str, ...] = (
    "growth_occ",
    "growth_pop",
    "rate",
    "scale",
    "ratio_stability",
)
BASE_COMPONENTS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "population",
)
ERROR_QUANTITIES: tuple[str, ...] = (
    "employed",
    "unemployed",
    "working_age",
    "population",
)
GUARDED_RULE_STATUS = "pareto_with_guards"
EXCEPTION_STATUS = "exception_keeps_incumbent"
_GUARD_EPSILON = 1e-12
_POPULATION_EPSILON = 1e-8


class DonorSelectionError(ValueError):
    """Raised when donor selection inputs are inconsistent."""


@dataclass(frozen=True)
class DonorPolicy:
    """Settings of the donor analysis (see ``configs/*/urban.toml``)."""

    recipient_codes: Sequence[int]
    excluded_codes: Sequence[int]
    selection_years: Sequence[int]
    holdout_year: int
    seam_year: int
    history_start: int
    history_end: int
    proxy_last_year: int
    published_unit_persons: float
    guard_tolerance_log: float
    validation_quantile: float
    pareto_tolerance: float
    tie_break_weights: Sequence[float]
    minimax_weight: float
    incumbent_score_weights: Sequence[float]
    normalization_low_quantile: float
    normalization_high_quantile: float
    normalization_min_scale: float

    def __post_init__(self) -> None:
        """Validate weight vectors and quantiles."""
        for name in ("tie_break_weights", "incumbent_score_weights"):
            if len(getattr(self, name)) != len(FEATURES):
                raise ValueError(f"{name} needs one weight per criterion")
        if not 0 < self.validation_quantile < 1:
            raise ValueError("validation_quantile must be in (0, 1)")

    @property
    def history_years(self) -> list[int]:
        """Return the reconstructed (donor-trajectory) years."""
        return list(range(self.history_start, self.history_end + 1))


def pareto_efficient(losses: np.ndarray, tolerance: float) -> np.ndarray:
    """Return a mask of non-dominated rows (every column is minimized).

    Raises
    ------
    ValueError
        If the matrix is not finite and two-dimensional.
    """
    matrix = np.asarray(losses, dtype=float)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("A finite [alternatives, criteria] matrix is needed")
    dominated = np.zeros(len(matrix), dtype=bool)
    for row, candidate in enumerate(matrix):
        dominated[row] = bool(
            np.any(
                np.all(matrix <= candidate + tolerance, axis=1)
                & np.any(matrix < candidate - tolerance, axis=1)
            )
        )
    return ~dominated


def pair_features(recipient: pd.DataFrame, donor: pd.DataFrame) -> np.ndarray:
    """Compute the five dissimilarity criteria of a recipient-donor pair.

    Both frames hold window proxies for the selection years.
    """
    growth_occ = np.abs(
        np.diff(np.log(recipient["employed"]))
        - np.diff(np.log(donor["employed"]))
    ).mean()
    growth_pop = np.abs(
        np.diff(np.log(recipient["population"]))
        - np.diff(np.log(donor["population"]))
    ).mean()

    def rates(frame: pd.DataFrame) -> np.ndarray:
        return np.vstack(
            [
                frame["unemployed"] / frame["labor_force"],
                frame["labor_force"] / frame["working_age"],
                frame["employed"] / frame["working_age"],
            ]
        ).T

    rate = np.abs(rates(recipient) - rates(donor)).mean()
    scale = np.abs(
        np.log(
            np.median(recipient["population"]) / np.median(donor["population"])
        )
    )
    stability = np.mean(
        [
            np.std(np.log(recipient[q] / donor[q]), ddof=1)
            for q in ("employed", "working_age", "population")
        ]
    )
    return np.asarray(
        [growth_occ, growth_pop, rate, scale, stability], dtype=float
    )


class DonorTransfer:
    """Rescale a donor's trajectory to a recipient's level."""

    def __init__(self, sources: UrbanSources, policy: DonorPolicy) -> None:
        """Store sources and policy."""
        self._sources = sources
        self._policy = policy

    def predict(
        self, recipient: int, donor: int, years: Sequence[int]
    ) -> pd.DataFrame:
        """Return the transferred trajectory for ``years``.

        The four free components are scaled by their own calibration
        factor; labor force and working age are derived by identity.
        """
        donor_history = self._sources.history[donor]
        recipient_proxies = self._sources.proxies[recipient]
        calibration = list(self._policy.selection_years)
        result = pd.DataFrame(index=pd.Index(list(years), name="year"))
        for component in BASE_COMPONENTS:
            donor_calibration = np.array(
                donor_history.loc[calibration, component], dtype=float
            )
            own_calibration = np.array(
                recipient_proxies.loc[calibration, component], dtype=float
            )
            alpha = own_calibration.sum() / donor_calibration.sum()
            result[component] = (
                np.array(
                    donor_history.loc[list(years), component], dtype=float
                )
                * alpha
            )
        result["labor_force"] = result["employed"] + result["unemployed"]
        result["working_age"] = result["labor_force"] + result["inactive"]
        return result

    def checks(self, recipient: int, donor: int) -> dict[str, Any]:
        """Holdout error, seam continuity and admissibility of a pair."""
        policy = self._policy
        trajectory = self.predict(recipient, donor, policy.history_years)
        proxies = self._sources.proxies[recipient]

        def log_errors(year: int) -> dict[str, float]:
            predicted = self.predict(recipient, donor, [year]).iloc[0]
            observed = proxies.loc[year]
            return {
                c: float(abs(np.log(predicted[c] / observed[c])))
                for c in BASE_COMPONENTS
            }

        holdout = log_errors(policy.holdout_year)
        seam = log_errors(policy.seam_year)
        population = np.array(trajectory["population"], dtype=float)
        working_age = np.array(trajectory["working_age"], dtype=float)
        values = np.array(trajectory, dtype=float)
        return {
            "holdout_error_mean": float(np.mean(list(holdout.values()))),
            "holdout_error_max": float(max(holdout.values())),
            "seam_error_mean": float(np.mean(list(seam.values()))),
            "seam_error_max": float(max(seam.values())),
            "complete": bool(np.isfinite(values).all()),
            "positive": bool((values > 0).all()),
            "working_age_below_population": bool(
                np.all(working_age <= population + _POPULATION_EPSILON)
            ),
            "max_working_age_share": float(np.max(working_age / population)),
            **{f"holdout_error_{c}": holdout[c] for c in BASE_COMPONENTS},
        }

    def wape_against_history(
        self, recipient: int, donor: int
    ) -> dict[str, float]:
        """Weighted absolute percentage errors on a city with history."""
        years = self._policy.history_years
        predicted = self.predict(recipient, donor, years)
        truth = self._sources.history[recipient].loc[years]
        errors = {}
        for quantity in ERROR_QUANTITIES:
            estimate = np.array(predicted[quantity], dtype=float)
            actual = np.array(truth[quantity], dtype=float)
            errors[quantity] = float(
                np.abs(estimate - actual).sum() / np.abs(actual).sum()
            )
        return errors


@dataclass(frozen=True)
class DonorSelectionResult:
    """Ranked alternatives, the frozen catalog and the backtest."""

    alternatives: pd.DataFrame
    catalog: pd.DataFrame
    backtest: pd.DataFrame
    thresholds: Mapping[str, float]
    normalization: Mapping[str, Mapping[str, float]]


class ParetoDonorSelector:
    """Rank donors and select one per recipient with guards."""

    def __init__(
        self,
        sources: UrbanSources,
        policy: DonorPolicy,
        city_names: Mapping[int, str],
    ) -> None:
        """Compose the trajectory transfer with the selection policy."""
        self._sources = sources
        self._policy = policy
        self._names = dict(city_names)
        self._transfer = DonorTransfer(sources, policy)
        recipients = set(policy.recipient_codes)
        self._donors = sorted(set(city_names) - recipients)
        missing = set(self._donors) - set(sources.history)
        if missing:
            raise DonorSelectionError(f"Donors without history: {missing}")

    @property
    def transfer(self) -> DonorTransfer:
        """Return the trajectory transfer component."""
        return self._transfer

    def rank_pairs(self) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
        """Compute criteria, normalized scores, Pareto flags and regrets."""
        policy = self._policy
        years = list(policy.selection_years)
        windows = {
            code: frame.loc[years]
            for code, frame in self._sources.proxies.items()
        }
        rows = []
        for recipient in sorted(self._names):
            for donor in self._donors:
                if recipient == donor:
                    continue
                values = pair_features(windows[recipient], windows[donor])
                rows.append(
                    {
                        "recipient_code": recipient,
                        "donor_code": donor,
                        **dict(zip(FEATURES, values, strict=True)),
                        "population_ratio": float(
                            np.median(windows[recipient]["population"])
                            / np.median(windows[donor]["population"])
                        ),
                    }
                )
        pairs = pd.DataFrame(rows)
        known = pairs[pairs["recipient_code"].isin(self._donors)]
        low, high = (
            policy.normalization_low_quantile,
            policy.normalization_high_quantile,
        )
        scale = {
            f: float(
                max(
                    known[f].quantile(high) - known[f].quantile(low),
                    policy.normalization_min_scale,
                )
            )
            for f in FEATURES
        }
        floor = {f: float(known[f].quantile(low)) for f in FEATURES}
        for feature in FEATURES:
            pairs[f"{feature}_norm"] = np.maximum(
                0, (pairs[feature] - floor[feature]) / scale[feature]
            )
        pairs["score_incumbent_rule"] = sum(
            pairs[f"{f}_norm"] * w
            for f, w in zip(
                FEATURES, policy.incumbent_score_weights, strict=True
            )
        )
        return self._decorate(pairs, scale), {"scale": scale, "floor": floor}

    def _decorate(
        self, pairs: pd.DataFrame, scale: Mapping[str, float]
    ) -> pd.DataFrame:
        weights = np.asarray(self._policy.tie_break_weights, dtype=float)
        scales = np.array([scale[f] for f in FEATURES])
        decorated = []
        for _, group in pairs.groupby("recipient_code", sort=True):
            group = group.sort_values("donor_code").reset_index(drop=True)
            losses = np.array(group[list(FEATURES)], dtype=float)
            regret = (losses - losses.min(axis=0)) / scales
            group["pareto_efficient"] = pareto_efficient(
                losses, self._policy.pareto_tolerance
            )
            group["max_regret"] = regret.max(axis=1)
            group["weighted_regret"] = regret @ weights
            group["score_minimax"] = (
                group["max_regret"]
                + self._policy.minimax_weight * group["weighted_regret"]
            )
            group["score_distance"] = np.sqrt((regret**2) @ weights)
            for position, feature in enumerate(FEATURES):
                group[f"regret_{feature}"] = regret[:, position]
            decorated.append(group)
        return pd.concat(decorated, ignore_index=True)

    def choose_guarded(
        self, ranked: pd.DataFrame, recipient: int, incumbent: int
    ) -> tuple[int, str]:
        """Choose among efficient donors passing both guards.

        If none passes, the incumbent is kept as a traceable exception.
        """
        group = ranked[ranked["recipient_code"] == recipient]
        reference = self._transfer.checks(recipient, incumbent)
        tolerance = self._policy.guard_tolerance_log + _GUARD_EPSILON
        admissible = []
        for donor in group.loc[group["pareto_efficient"], "donor_code"]:
            candidate = self._transfer.checks(recipient, int(donor))
            if (
                candidate["holdout_error_mean"]
                <= reference["holdout_error_mean"] + tolerance
                and candidate["seam_error_mean"]
                <= reference["seam_error_mean"] + tolerance
                and candidate["complete"]
                and candidate["positive"]
                and candidate["working_age_below_population"]
            ):
                admissible.append(int(donor))
        if not admissible:
            return incumbent, EXCEPTION_STATUS
        options = group[group["donor_code"].isin(admissible)]
        best = options.sort_values(["score_distance", "donor_code"]).iloc[0]
        return int(best["donor_code"]), GUARDED_RULE_STATUS

    def run(self, reference_donors: Mapping[int, int]) -> DonorSelectionResult:
        """Rank, evaluate, select and backtest."""
        missing = set(self._policy.recipient_codes) - set(reference_donors)
        if missing:
            raise DonorSelectionError(f"No reference donor for {missing}")
        ranked, normalization = self.rank_pairs()
        recipients = sorted(self._policy.recipient_codes)
        checks = pd.DataFrame(
            [
                {
                    "recipient_code": r,
                    "donor_code": d,
                    **self._transfer.checks(r, d),
                }
                for r in recipients
                for d in self._donors
            ]
        )
        alternatives = ranked[ranked["recipient_code"].isin(recipients)].merge(
            checks, on=["recipient_code", "donor_code"], validate="one_to_one"
        )
        alternatives["is_reference_donor"] = [
            reference_donors[r] == d
            for r, d in zip(
                alternatives["recipient_code"],
                alternatives["donor_code"],
                strict=True,
            )
        ]
        catalog = pd.DataFrame(
            [
                self._catalog_row(alternatives, r, reference_donors[r])
                for r in recipients
            ]
        )
        backtest = self._backtest(ranked)
        quantile = self._policy.validation_quantile
        thresholds = {
            "seam_error_quantile": float(
                backtest["seam_error_mean"].quantile(quantile)
            ),
            "holdout_error_quantile": float(
                backtest["holdout_error_mean"].quantile(quantile)
            ),
        }
        return DonorSelectionResult(
            alternatives=alternatives,
            catalog=catalog,
            backtest=backtest,
            thresholds=thresholds,
            normalization=normalization,
        )

    def _catalog_row(
        self, alternatives: pd.DataFrame, recipient: int, incumbent: int
    ) -> dict[str, Any]:
        selected, status = self.choose_guarded(
            alternatives, recipient, incumbent
        )
        group = alternatives[alternatives["recipient_code"] == recipient]
        old = group[group["donor_code"] == incumbent].iloc[0]
        chosen = group[group["donor_code"] == selected].iloc[0]
        frontier = group[group["pareto_efficient"]].sort_values(
            ["score_minimax", "donor_code"]
        )
        backups = [int(d) for d in frontier["donor_code"] if d != selected]
        backups = backups[:2]
        while len(backups) < 2:
            rest = group[~group["donor_code"].isin([selected, *backups])]
            backups.append(
                int(rest.sort_values("score_minimax").iloc[0]["donor_code"])
            )
        chosen_losses = np.array(chosen[list(FEATURES)], dtype=float)
        old_losses = np.array(old[list(FEATURES)], dtype=float)
        dominates = bool(
            np.all(chosen_losses <= old_losses + _GUARD_EPSILON)
            and np.any(chosen_losses < old_losses - _GUARD_EPSILON)
        )
        return {
            "recipient_code": recipient,
            "recipient_name": self._names[recipient],
            "reference_donor_code": incumbent,
            "reference_donor_name": self._names[incumbent],
            "selected_donor_code": selected,
            "selected_donor_name": self._names[selected],
            "backup_1_code": backups[0],
            "backup_1_name": self._names[backups[0]],
            "backup_2_code": backups[1],
            "backup_2_name": self._names[backups[1]],
            "frontier_size": int(len(frontier)),
            "reference_in_frontier": bool(old["pareto_efficient"]),
            "selected_dominates_reference": dominates,
            "score_minimax_reference": float(old["score_minimax"]),
            "score_minimax_selected": float(chosen["score_minimax"]),
            "holdout_error_reference": float(old["holdout_error_mean"]),
            "holdout_error_selected": float(chosen["holdout_error_mean"]),
            "seam_error_reference": float(old["seam_error_mean"]),
            "seam_error_selected": float(chosen["seam_error_mean"]),
            "max_working_age_share_selected": float(
                chosen["max_working_age_share"]
            ),
            "positive_selected": bool(chosen["positive"]),
            "selection_status": status,
        }

    def _backtest(self, ranked: pd.DataFrame) -> pd.DataFrame:
        """Apply the guarded rule to the 23 cities whose past is known."""
        rows = []
        for city in self._donors:
            group = ranked[ranked["recipient_code"] == city]
            incumbent = int(
                group.sort_values(["score_incumbent_rule", "donor_code"]).iloc[
                    0
                ]["donor_code"]
            )
            donor, _ = self.choose_guarded(ranked, city, incumbent)
            errors = self._transfer.wape_against_history(city, donor)
            checks = self._transfer.checks(city, donor)
            rows.append(
                {
                    "city_code": city,
                    "city_name": self._names[city],
                    "donor_code": donor,
                    "donor_name": self._names[donor],
                    "wape_balanced": float(np.mean(list(errors.values()))),
                    "wape_max_quantity": float(max(errors.values())),
                    **{f"wape_{q}": errors[q] for q in ERROR_QUANTITIES},
                    "holdout_error_mean": checks["holdout_error_mean"],
                    "seam_error_mean": checks["seam_error_mean"],
                }
            )
        return pd.DataFrame(rows)
