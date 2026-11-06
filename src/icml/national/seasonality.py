"""Transfer of the GEIH seasonal pattern to the reconstructed history.

The reconstructed 1993-2000 months inherit the (weak) seasonality of their
indicators. This stage estimates, with a robust STL decomposition, the
log-seasonal profile of each component share (employed, unemployed and
inactive over working age) both in the history and in an observed GEIH
reference window. A fraction (``strength``) of the profile difference is
applied, and an iterative proportional fitting (IPF) step restores the
monthly working age and the annual mean of every component exactly.
Months after the history window are never modified.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from icml.national.reconciliation import with_derived_quantities
from icml.national.schema import PERIOD_COLUMN, QUANTITY_COLUMNS

COMPONENTS: tuple[str, ...] = ("employed", "unemployed", "inactive")
_MONTHS_PER_YEAR = 12
_MIN_STL_MONTHS = 36
_IDENTITY_TOLERANCE = 1e-6
_ANNUAL_TOLERANCE = 1e-5
_POPULATION_TOLERANCE = 1e-7
_TEMPLATE_COMPARISON_SLACK = 1e-12


class SeasonalityError(ValueError):
    """Raised when the seasonal transfer cannot be applied."""


@dataclass(frozen=True)
class SeasonalityPolicy:
    """Settings of the seasonal pattern transfer.

    Attributes
    ----------
    history_start, history_end : int
        Years whose months are adjusted.
    template_from, template_through : int
        Observed years used to estimate the target profile.
    strength : float
        Share of the profile difference applied, in ``[0, 1]``.
    seasonal_window, trend_window : int
        STL smoother lengths (odd integers).
    ipf_tolerance : float
        Convergence tolerance of the proportional fitting, in persons.
    ipf_max_iterations : int
        Iteration cap of the proportional fitting.
    max_relative_monthly_intervention : float
        Review threshold (reported).
    max_added_splice_log : float
        Review threshold for the extra seam jump (reported).
    """

    history_start: int
    history_end: int
    template_from: int
    template_through: int
    strength: float
    seasonal_window: int
    trend_window: int
    ipf_tolerance: float
    ipf_max_iterations: int
    max_relative_monthly_intervention: float
    max_added_splice_log: float

    def __post_init__(self) -> None:
        """Validate ranges."""
        if not 0 <= self.strength <= 1:
            raise ValueError("strength must be in [0, 1]")
        if self.history_end < self.history_start:
            raise ValueError("history_end precedes history_start")
        if self.template_through < self.template_from:
            raise ValueError("template_through precedes template_from")


@dataclass(frozen=True)
class SeasonalityResult:
    """Adjusted series and audit outputs."""

    monthly: pd.DataFrame
    profiles: pd.DataFrame
    seam: pd.DataFrame
    levels: pd.DataFrame
    quality: Mapping[str, bool]
    diagnostics: Mapping[str, Any]


def _indexed(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if PERIOD_COLUMN not in frame.columns:
        raise SeasonalityError(f"{name}: missing {PERIOD_COLUMN}")
    if frame[PERIOD_COLUMN].duplicated().any():
        raise SeasonalityError(f"{name}: duplicated months")
    data = frame.copy()
    data.index = pd.PeriodIndex(data[PERIOD_COLUMN].astype(str), freq="M")
    if not data.index.is_monotonic_increasing:
        raise SeasonalityError(f"{name}: months must be sorted")
    values = np.array(data[list(QUANTITY_COLUMNS)], dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise SeasonalityError(f"{name}: values must be finite and positive")
    return data


def proportional_fit(
    seed: np.ndarray,
    row_totals: np.ndarray,
    column_totals: np.ndarray,
    *,
    tolerance: float,
    max_iterations: int,
) -> tuple[np.ndarray, int]:
    """Biproportional (RAS / IPF) fit of a positive matrix to its margins.

    Parameters
    ----------
    seed : numpy.ndarray
        Positive ``months x components`` matrix.
    row_totals : numpy.ndarray
        Required row sums (monthly working age).
    column_totals : numpy.ndarray
        Required column sums (annual totals of each component).
    tolerance : float
        Maximum absolute margin error at convergence.
    max_iterations : int
        Iteration cap.

    Returns
    -------
    tuple[numpy.ndarray, int]
        Fitted matrix and number of iterations used.

    Raises
    ------
    SeasonalityError
        If inputs are not positive, margins are incompatible, or the
        algorithm does not converge.
    """
    if (
        (seed <= 0).any()
        or (row_totals <= 0).any()
        or (column_totals <= 0).any()
    ):
        raise SeasonalityError("IPF requires strictly positive inputs")
    if abs(float(row_totals.sum() - column_totals.sum())) > 2e-5:
        raise SeasonalityError("Row and column margins are incompatible")
    fitted = seed.copy()
    for iteration in range(max_iterations):
        fitted *= (row_totals / fitted.sum(axis=1))[:, None]
        fitted *= (column_totals / fitted.sum(axis=0))[None, :]
        error = max(
            np.max(np.abs(fitted.sum(axis=1) - row_totals)),
            np.max(np.abs(fitted.sum(axis=0) - column_totals)),
        )
        if error < tolerance:
            return fitted, iteration + 1
    raise SeasonalityError("Proportional fitting did not converge")


class SeasonalPatternTransfer:
    """Apply the observed seasonal pattern to the reconstructed history."""

    def __init__(self, policy: SeasonalityPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def seasonal_profiles(
        self, frame: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
        """Return the centered log-seasonal profile of each component share.

        Raises
        ------
        SeasonalityError
            If fewer than 36 months are available.
        """
        if len(frame) < _MIN_STL_MONTHS:
            raise SeasonalityError("STL needs at least 36 consecutive months")
        profiles: dict[str, np.ndarray] = {}
        quality: dict[str, dict[str, float]] = {}
        working_age = np.array(frame["working_age"], dtype=float)
        for component in COMPONENTS:
            share = np.log(
                np.array(frame[component], dtype=float) / working_age
            )
            decomposition = STL(
                share,
                period=_MONTHS_PER_YEAR,
                seasonal=self._policy.seasonal_window,
                trend=self._policy.trend_window,
                robust=True,
            ).fit()
            seasonal = pd.Series(
                np.asarray(decomposition.seasonal), index=frame.index
            )
            profile = np.array(
                seasonal.groupby(seasonal.index.month)
                .median()
                .reindex(range(1, _MONTHS_PER_YEAR + 1)),
                dtype=float,
            )
            profile = profile - profile.mean()
            profiles[component] = profile
            quality[component] = {
                "amplitude_log": float(profile.max() - profile.min()),
                "seasonal_std_log": float(np.std(profile)),
                "n_months": len(frame),
            }
        table = pd.DataFrame(
            profiles,
            index=pd.Index(range(1, _MONTHS_PER_YEAR + 1), name="month"),
        )
        return table, quality

    def adjust(
        self, monthly: pd.DataFrame, observed: pd.DataFrame
    ) -> SeasonalityResult:
        """Adjust the history window of ``monthly``.

        Parameters
        ----------
        monthly : pandas.DataFrame
            Reconciled monthly series covering the history window.
        observed : pandas.DataFrame
            Observed GEIH months covering the template window and the
            first month after the history.

        Raises
        ------
        SeasonalityError
            If windows are incomplete or the fitting fails.
        """
        policy = self._policy
        base = _indexed(monthly, "monthly")
        reference_all = _indexed(observed, "observed")
        history = base.loc[str(policy.history_start) : str(policy.history_end)]
        reference = reference_all.loc[
            str(policy.template_from) : str(policy.template_through)
        ]
        n_history = (policy.history_end - policy.history_start + 1) * 12
        n_reference = (policy.template_through - policy.template_from + 1) * 12
        if len(history) != n_history:
            raise SeasonalityError("History window incomplete")
        if len(reference) != n_reference:
            raise SeasonalityError("Template window incomplete")
        first_after = pd.Period(f"{policy.history_end + 1}-01", freq="M")
        if first_after not in reference_all.index:
            raise SeasonalityError(
                "First observed month after history "
                "is required to audit the seam"
            )

        old_profile, old_quality = self.seasonal_profiles(history)
        template, template_quality = self.seasonal_profiles(reference)
        updated = base.copy()
        iterations = []
        for year, section in history.groupby(history.index.year):
            month_index = section.index.month.to_numpy() - 1
            delta = (
                template.to_numpy()[month_index]
                - old_profile.to_numpy()[month_index]
            )
            seed = np.array(section[list(COMPONENTS)], dtype=float) * np.exp(
                policy.strength * delta
            )
            fitted, n_iterations = proportional_fit(
                seed,
                np.array(section["working_age"], dtype=float),
                np.array(section[list(COMPONENTS)].sum(), dtype=float),
                tolerance=policy.ipf_tolerance,
                max_iterations=policy.ipf_max_iterations,
            )
            updated.loc[section.index, list(COMPONENTS)] = fitted
            iterations.append(
                {"year": int(year), "ipf_iterations": n_iterations}
            )
        updated = with_derived_quantities(updated)
        after_history = base.index.year > policy.history_end
        updated.loc[after_history, list(QUANTITY_COLUMNS)] = base.loc[
            after_history, list(QUANTITY_COLUMNS)
        ]
        return self._assemble(
            base,
            updated,
            reference_all,
            old_profile,
            template,
            old_quality,
            template_quality,
            iterations,
            after_history,
            first_after,
        )

    def _assemble(
        self,
        base: pd.DataFrame,
        updated: pd.DataFrame,
        observed: pd.DataFrame,
        old_profile: pd.DataFrame,
        template: pd.DataFrame,
        old_quality: dict[str, dict[str, float]],
        template_quality: dict[str, dict[str, float]],
        iterations: list[dict[str, int]],
        after_history: np.ndarray,
        first_after: pd.Period,
    ) -> SeasonalityResult:
        policy = self._policy
        quantities = list(QUANTITY_COLUMNS)
        changes = updated[quantities] - base[quantities]
        in_history = ~after_history
        relative = (updated[quantities] / base[quantities] - 1)[in_history]
        identity_gap = max(
            (
                updated["labor_force"]
                - updated["employed"]
                - updated["unemployed"]
            )
            .abs()
            .max(),
            (
                updated["working_age"]
                - updated["labor_force"]
                - updated["inactive"]
            )
            .abs()
            .max(),
        )
        annual_new = (
            updated[in_history]
            .groupby(updated[in_history].index.year)[quantities]
            .mean()
        )
        annual_old = (
            base[in_history]
            .groupby(base[in_history].index.year)[quantities]
            .mean()
        )
        annual_gap = float(np.max(np.abs(np.array(annual_new - annual_old))))

        last_history = first_after - 1
        seam = pd.DataFrame(
            [
                {
                    "quantity": q,
                    "before_log_change": float(
                        np.log(
                            observed.loc[first_after, q]
                            / base.loc[last_history, q]
                        )
                    ),
                    "after_log_change": float(
                        np.log(
                            observed.loc[first_after, q]
                            / updated.loc[last_history, q]
                        )
                    ),
                }
                for q in quantities
            ]
        )
        seam["added_log_change"] = (
            seam["after_log_change"] - seam["before_log_change"]
        )

        history_slice = updated.loc[
            str(policy.history_start) : str(policy.history_end)
        ]
        new_profile, new_quality = self.seasonal_profiles(history_slice)
        error_before = np.sqrt(
            np.mean(
                (old_profile.to_numpy() - template.to_numpy()) ** 2, axis=0
            )
        )
        error_after = np.sqrt(
            np.mean(
                (new_profile.to_numpy() - template.to_numpy()) ** 2, axis=0
            )
        )
        profiles = pd.concat(
            [
                old_profile.add_prefix("before_"),
                template.add_prefix("geih_"),
                new_profile.add_prefix("after_"),
            ],
            axis=1,
        ).reset_index()

        levels = pd.DataFrame(
            {
                PERIOD_COLUMN: base[PERIOD_COLUMN].to_numpy(),
                "year": base.index.year,
            }
        )
        for q in quantities:
            levels[f"{q}_before"] = base[q].to_numpy()
            levels[f"{q}_after"] = updated[q].to_numpy()
            levels[f"{q}_delta"] = changes[q].to_numpy()

        max_relative = float(np.abs(np.array(relative)).max())
        max_seam = float(seam["added_log_change"].abs().max())
        quality = {
            "observed_reference_not_changed": bool(
                updated.loc[after_history, quantities].equals(
                    base.loc[after_history, quantities]
                )
            ),
            "no_missing_or_negative": bool(
                np.isfinite(np.array(updated[quantities], dtype=float)).all()
                and (updated[quantities] > 0).all().all()
            ),
            "working_age_not_above_population": bool(
                (
                    updated["working_age"]
                    <= updated["population"] + _POPULATION_TOLERANCE
                ).all()
            ),
            "identities_closed": bool(identity_gap < _IDENTITY_TOLERANCE),
            "annual_anchors_preserved": annual_gap < _ANNUAL_TOLERANCE,
            "seasonal_template_match_not_worse": bool(
                np.all(
                    error_after <= error_before + _TEMPLATE_COMPARISON_SLACK
                )
            ),
            "monthly_intervention_under_review_limit": max_relative
            <= policy.max_relative_monthly_intervention,
            "added_splice_jump_under_review_limit": max_seam
            <= policy.max_added_splice_log,
        }
        diagnostics = {
            "max_abs_monthly_persons_delta": float(
                np.max(np.abs(np.array(changes[in_history])))
            ),
            "max_abs_monthly_relative_delta": max_relative,
            "max_annual_anchor_delta_persons": annual_gap,
            "max_accounting_identity_gap_persons": float(identity_gap),
            "max_added_splice_log": max_seam,
            "template_fit_log_rmse_before": dict(
                zip(COMPONENTS, map(float, error_before), strict=True)
            ),
            "template_fit_log_rmse_after": dict(
                zip(COMPONENTS, map(float, error_after), strict=True)
            ),
            "template_source_quality": template_quality,
            "history_source_quality": old_quality,
            "updated_profile_quality": new_quality,
            "ipf_convergence": iterations,
        }
        return SeasonalityResult(
            monthly=updated.reset_index(drop=True)[
                [PERIOD_COLUMN, *quantities]
            ],
            profiles=profiles,
            seam=seam,
            levels=levels,
            quality=quality,
            diagnostics=diagnostics,
        )
