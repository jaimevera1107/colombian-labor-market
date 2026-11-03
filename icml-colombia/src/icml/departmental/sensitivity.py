"""Sensitivity of a departmental series to a competing Chow-Lin optimum.

RC1 found two likelihood peaks for Cundinamarca's inactive population. The
global maximum is kept; this audit re-fits with the competing rho fixed and
records the monthly difference, without declaring the solution unique.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import pandas as pd
from tempdisagg import TemporalDisaggregator


class SensitivityError(ValueError):
    """Raised when either fit fails to preserve the annual anchors."""


@dataclass(frozen=True)
class RhoSensitivityPolicy:
    """Territory, series and competing rho of the audit."""

    territory_code: int
    quantity: str
    competing_rho: float


@dataclass(frozen=True)
class RhoSensitivityResult:
    """Monthly comparison, likelihood profile and summary."""

    series: pd.DataFrame
    profile: pd.DataFrame
    summary: dict[str, Any]


class RhoSensitivityAudit:
    """Compare the global Chow-Lin fit with a fixed competing rho."""

    def __init__(
        self,
        policy: RhoSensitivityPolicy,
        method: str,
        include_intercept: bool,
        anchor_tolerance_persons: float,
        fit_start: str,
        fit_end: str,
    ) -> None:
        """Store settings shared with the reconstruction."""
        self._policy = policy
        self._method = method
        self._intercept = include_intercept
        self._tolerance = anchor_tolerance_persons
        self._window = (fit_start, fit_end)

    def run(
        self, anchors: pd.DataFrame, national: pd.DataFrame
    ) -> RhoSensitivityResult:
        """Fit both models and compare them."""
        policy = self._policy
        reference = national.copy()
        reference.index = pd.PeriodIndex(
            reference["period"].astype(str), freq="M"
        )
        indicator = reference.loc[
            self._window[0] : self._window[1], [policy.quantity]
        ].astype(float)
        territory = anchors[
            anchors["dep_code"] == policy.territory_code
        ].sort_values("year")
        annual = pd.Series(
            territory[policy.quantity].to_numpy(dtype=float),
            index=pd.PeriodIndex(territory["year"].astype(str), freq="Y"),
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            global_fit = TemporalDisaggregator(
                self._method,
                conversion="average",
                include_intercept=self._intercept,
                completion=False,
            ).fit(annual, indicator)
        fixed_fit = TemporalDisaggregator(
            self._method,
            conversion="average",
            include_intercept=self._intercept,
            completion=False,
            rho_method="fixed",
            fixed_rho=policy.competing_rho,
        ).fit(annual, indicator)
        if (
            global_fit.rho is None
            or global_fit.regression is None
            or fixed_fit.regression is None
        ):
            raise SensitivityError("The method does not estimate rho")
        global_values = global_fit.values  # noqa: PD011
        fixed_values = fixed_fit.values  # noqa: PD011
        for name, values in (
            ("global", global_values),
            ("fixed", fixed_values),
        ):
            gap = (
                values.groupby(values.index.asfreq("Y"))
                .mean()
                .sub(annual)
                .abs()
                .max()
            )
            if float(gap) > self._tolerance:
                raise SensitivityError(f"{name} fit lost annual anchors")
        difference = (fixed_values - global_values) / global_values * 100
        series = pd.DataFrame(
            {
                "period": global_values.index.astype(str),
                "global_rho_value": global_values.to_numpy(dtype=float),
                "competing_rho_value": fixed_values.to_numpy(dtype=float),
                "difference_pct": difference.to_numpy(dtype=float),
            }
        )
        likelihood = global_fit.rho.profile
        if likelihood is None:
            raise SensitivityError("The fit did not return a rho profile")
        profile = pd.DataFrame(
            {
                "rho": likelihood.index.to_numpy(dtype=float),
                "negative_loglik": likelihood.to_numpy(dtype=float),
            }
        )
        summary = {
            "rho_global": float(global_fit.rho.value),
            "rho_competing": policy.competing_rho,
            "log_likelihood_global": float(
                global_fit.regression.log_likelihood
            ),
            "log_likelihood_competing": float(
                fixed_fit.regression.log_likelihood
            ),
            "max_abs_monthly_difference_pct": float(difference.abs().max()),
            "mean_abs_monthly_difference_pct": float(difference.abs().mean()),
            "local_minima": [float(v) for v in global_fit.rho.local_minima],
        }
        return RhoSensitivityResult(
            series=series, profile=profile, summary=summary
        )
