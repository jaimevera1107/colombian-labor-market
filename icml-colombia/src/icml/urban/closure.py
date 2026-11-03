"""Bounded closure of the estimated recipient histories (annual panel).

The transferred history of a recipient (2007-2020) may not connect with its
first window proxy. The seam residual of each component is shrunk radially
to a target mean, capped, and spread as a log-linear ramp over the last
historical years. Proxies (2021 onward) and years before the ramp are never
modified.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.urban.accounting import URBAN_SIGNALS
from icml.urban.donors import BASE_COMPONENTS, DonorPolicy, DonorTransfer
from icml.urban.inputs import UrbanSources

ORIGIN_ESTIMATED = "ESTIMADO_RETROPOLADO"
ORIGIN_REGULARIZED = "ESTIMADO_RETROPOLADO_REGULARIZADO"
ORIGIN_PROXY = "PROXY_VENTANAS_NO_ANUAL"
ORIGIN_PROXY_PROVISIONAL = "PROXY_2026_PROVISIONAL"
_IDENTITY_TOLERANCE = 1e-6


class ClosureError(ValueError):
    """Raised when the closure would break its constraints."""


@dataclass(frozen=True)
class BridgePolicy:
    """Bounds of the seam regularization."""

    start_year: int
    end_year: int
    target_mean_log: float
    max_terminal_log_change: float
    max_extra_log_growth: float
    tolerance: float

    @property
    def ramp_years(self) -> list[int]:
        """Return the years over which the ramp is applied."""
        return list(range(self.start_year, self.end_year + 1))


def close_bridge(
    trajectory: pd.DataFrame,
    recipient_proxies: pd.DataFrame,
    donor_history: pd.DataFrame,
    policy: BridgePolicy,
    seam_year: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Regularize the seam between a transferred history and its proxies.

    Returns
    -------
    tuple[pandas.DataFrame, dict]
        Adjusted trajectory and diagnostics.

    Raises
    ------
    ClosureError
        If the required yearly growth exceeds the methodological limit.
    """
    last_year = seam_year - 1
    adjusted = trajectory.copy()
    residual = {
        c: float(
            np.log(
                float(recipient_proxies.loc[seam_year, c])
                / (
                    float(adjusted.loc[last_year, c])
                    * float(
                        donor_history.loc[seam_year, c]
                        / donor_history.loc[last_year, c]
                    )
                )
            )
        )
        for c in BASE_COMPONENTS
    }
    initial = float(np.mean(np.abs(list(residual.values()))))
    fraction = (
        0.0
        if initial <= policy.target_mean_log
        else 1 - policy.target_mean_log / initial
    )
    deltas = {
        c: float(
            np.clip(
                r * fraction,
                -policy.max_terminal_log_change,
                policy.max_terminal_log_change,
            )
        )
        for c, r in residual.items()
    }
    years = policy.ramp_years
    ramps = np.linspace(1 / len(years), 1.0, len(years))
    if any(
        abs(d) / len(years) > policy.max_extra_log_growth + policy.tolerance
        for d in deltas.values()
    ):
        raise ClosureError("Required yearly change exceeds the limit")
    for component, delta in deltas.items():
        adjusted.loc[years, component] = np.array(
            adjusted.loc[years, component], dtype=float
        ) * np.exp(delta * ramps)
    adjusted["labor_force"] = adjusted["employed"] + adjusted["unemployed"]
    adjusted["working_age"] = adjusted["labor_force"] + adjusted["inactive"]
    residual_after = {c: r - deltas[c] for c, r in residual.items()}
    after = float(np.mean(np.abs(list(residual_after.values()))))
    values = np.array(adjusted[list(URBAN_SIGNALS)], dtype=float)
    coherent = bool(
        np.isfinite(values).all()
        and (values > 0).all()
        and (
            adjusted["working_age"]
            <= adjusted["population"] + policy.tolerance
        ).all()
        and np.allclose(
            adjusted["labor_force"],
            adjusted["employed"] + adjusted["unemployed"],
            atol=_IDENTITY_TOLERANCE,
            rtol=0,
        )
        and np.allclose(
            adjusted["working_age"],
            adjusted["labor_force"] + adjusted["inactive"],
            atol=_IDENTITY_TOLERANCE,
            rtol=0,
        )
    )
    before_ramp = trajectory.index < policy.start_year
    diagnostics = {
        "seam_before": initial,
        "seam_after": after,
        **{f"delta_log_{c}": deltas[c] for c in BASE_COMPONENTS},
        "max_delta_log": float(max(abs(d) for d in deltas.values())),
        "max_extra_growth_log": float(
            max(abs(d) for d in deltas.values()) / len(years)
        ),
        "coherent": coherent,
        "target_met": bool(after <= policy.target_mean_log + policy.tolerance),
        "untouched_before_ramp": bool(
            adjusted.loc[before_ramp, list(URBAN_SIGNALS)].equals(
                trajectory.loc[before_ramp, list(URBAN_SIGNALS)]
            )
        ),
    }
    return adjusted, diagnostics


@dataclass(frozen=True)
class ClosureResult:
    """Closed annual panel of the recipients and its audit."""

    panel: pd.DataFrame
    audit: pd.DataFrame


class RecipientPanelBuilder:
    """Build the closed 2007-2026 annual panel of the nine recipients."""

    def __init__(
        self,
        sources: UrbanSources,
        donor_policy: DonorPolicy,
        bridge_policy: BridgePolicy,
    ) -> None:
        """Compose the transfer and the bridge policy."""
        self._sources = sources
        self._donor_policy = donor_policy
        self._bridge = bridge_policy
        self._transfer = DonorTransfer(sources, donor_policy)

    def build(
        self, catalog: pd.DataFrame, holdout_threshold: float
    ) -> ClosureResult:
        """Close every recipient in the catalog.

        Raises
        ------
        ClosureError
            If any closure is incoherent, misses its target, or changes
            proxies or pre-ramp years.
        """
        policy = self._donor_policy
        panel_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []
        for row in catalog.sort_values("recipient_code").itertuples():
            code = int(row.recipient_code)
            donor = int(row.selected_donor_code)
            trajectory = self._transfer.predict(
                code, donor, policy.history_years
            )
            adjusted, diagnostics = close_bridge(
                trajectory,
                self._sources.proxies[code],
                self._sources.history[donor],
                self._bridge,
                policy.seam_year,
            )
            identity = {
                "recipient_code": code,
                "recipient_name": row.recipient_name,
                "donor_code": donor,
            }
            for year in policy.history_years:
                origin = (
                    ORIGIN_REGULARIZED
                    if year >= self._bridge.start_year
                    else ORIGIN_ESTIMATED
                )
                panel_rows.append(
                    {
                        **identity,
                        "year": year,
                        "origin": origin,
                        **adjusted.loc[year, list(URBAN_SIGNALS)].to_dict(),
                    }
                )
            for year in range(policy.seam_year, policy.proxy_last_year + 1):
                origin = (
                    ORIGIN_PROXY_PROVISIONAL
                    if year == policy.proxy_last_year
                    else ORIGIN_PROXY
                )
                panel_rows.append(
                    {
                        **identity,
                        "year": year,
                        "origin": origin,
                        **self._sources.proxies[code]
                        .loc[year, list(URBAN_SIGNALS)]
                        .to_dict(),
                    }
                )
            holdout = self._transfer.checks(code, donor)["holdout_error_mean"]
            warning = holdout > holdout_threshold
            audit_rows.append(
                {
                    **identity,
                    **diagnostics,
                    "holdout_error_log": float(holdout),
                    "holdout_warning": bool(warning),
                    "decision": "closure_audited"
                    if diagnostics["coherent"] and diagnostics["target_met"]
                    else "review_required",
                }
            )
        panel = (
            pd.DataFrame(panel_rows)
            .sort_values(["recipient_code", "year"])
            .reset_index(drop=True)
        )
        audit = pd.DataFrame(audit_rows)
        self._verify(panel, audit)
        return ClosureResult(panel=panel, audit=audit)

    def _verify(self, panel: pd.DataFrame, audit: pd.DataFrame) -> None:
        if not audit["coherent"].all():
            raise ClosureError("Closure produced incoherent values")
        if not audit["target_met"].all():
            raise ClosureError("Closure did not reach the seam target")
        if not audit["untouched_before_ramp"].all():
            raise ClosureError("Years before the ramp were modified")
        proxies = panel[panel["year"] >= self._donor_policy.seam_year]
        for code, group in proxies.groupby("recipient_code"):
            source = self._sources.proxies[int(code)].loc[
                list(group["year"]), list(URBAN_SIGNALS)
            ]
            if not np.array_equal(
                np.array(group[list(URBAN_SIGNALS)]), np.array(source)
            ):
                raise ClosureError(f"Proxies were modified for {code}")


def thresholds_from(result: Mapping[str, float]) -> float:
    """Return the holdout threshold used to flag recipients."""
    return float(result["holdout_error_quantile"])
