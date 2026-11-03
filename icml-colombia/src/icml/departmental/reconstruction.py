"""Monthly reconstruction of the anchored departments.

For each department and free component (employed, unemployed, inactive,
population), the official annual means are disaggregated to months with
Chow-Lin using the homologous national series as indicator. The result is
linked to the national series before the first anchored year with a
12-month ratio splice. Labor force and working age follow by identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from tempdisagg import SeriesSplicer, TemporalDisaggregator

from icml.national.disaggregation import require_tempdisagg_version

COMPONENTS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "population",
)
ORIGIN_BACKCAST = "INFERIDO_NACIONAL_SIN_ANCLA_DEPARTAMENTAL"
ORIGIN_ANCHORED = "CHOW_LIN_063_CON_ANCLA_OFICIAL_ANUAL"


class ReconstructionError(ValueError):
    """Raised when the departmental reconstruction breaks its contract."""


@dataclass(frozen=True)
class ReconstructionPolicy:
    """Calendar and model settings of the departmental reconstruction."""

    start_period: str
    anchor_start_period: str
    end_period: str
    method: str
    include_intercept: bool
    splice_overlap_months: int
    anchor_tolerance_persons: float


@dataclass(frozen=True)
class ReconstructionResult:
    """Monthly panel of the anchored departments and fit diagnostics."""

    panel: pd.DataFrame
    diagnostics: pd.DataFrame


class DepartmentalReconstruction:
    """Chow-Lin disaggregation plus national backcast per department."""

    def __init__(self, policy: ReconstructionPolicy) -> None:
        """Store the policy and build calendars."""
        self._policy = policy
        self._months = pd.period_range(
            policy.start_period, policy.end_period, freq="M"
        )
        self._fit_months = pd.period_range(
            policy.anchor_start_period, policy.end_period, freq="M"
        )

    def run(
        self, anchors: pd.DataFrame, national: pd.DataFrame
    ) -> ReconstructionResult:
        """Reconstruct every department in ``anchors``."""
        require_tempdisagg_version()
        reference = national.copy()
        reference.index = pd.PeriodIndex(
            reference["period"].astype(str), freq="M"
        )
        reference = reference.loc[self._months[0] : self._months[-1]]
        if not reference.index.equals(self._months):
            raise ReconstructionError("National series must cover window")
        frames, diagnostics = [], []
        for code, group in anchors.groupby("dep_code", sort=True):
            frame, records = self._department(
                int(code), group.sort_values("year"), reference
            )
            frames.append(frame)
            diagnostics.extend(records)
        panel = (
            pd.concat(frames, ignore_index=True)
            .sort_values(["dep_code", "period"])
            .reset_index(drop=True)
        )
        return ReconstructionResult(
            panel=panel, diagnostics=pd.DataFrame(diagnostics)
        )

    def _department(
        self, code: int, anchors: pd.DataFrame, national: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        policy = self._policy
        name = str(anchors.iloc[0]["department"])
        result = pd.DataFrame(
            index=self._months, columns=list(COMPONENTS), dtype=float
        )
        link_end = self._fit_months[11]
        records = []
        for component in COMPONENTS:
            annual = pd.Series(
                np.array(anchors[component], dtype=float),
                index=pd.PeriodIndex(anchors["year"].astype(str), freq="Y"),
                name=component,
            )
            indicator = national.loc[self._fit_months, [component]].astype(
                float
            )
            fit = TemporalDisaggregator(
                policy.method,
                conversion="average",
                include_intercept=policy.include_intercept,
                completion=False,
            ).fit(annual, indicator)
            monthly = fit.values.sort_index()  # noqa: PD011
            preprocessing = fit.preprocessing
            if (
                not monthly.index.equals(self._fit_months)
                or preprocessing.n_filled_values
                or len(preprocessing.added_periods)
            ):
                raise ReconstructionError(
                    f"Calendar or indicators altered: {name}/{component}"
                )
            errors = (
                monthly.groupby(monthly.index.asfreq("Y"))
                .mean()
                .reindex(annual.index)
                - annual
            )
            if errors.abs().max() > policy.anchor_tolerance_persons:
                raise ReconstructionError(
                    f"Annual anchors not kept: {name}/{component}"
                )
            splice = SeriesSplicer(
                method="ratio",
                overlap_periods=policy.splice_overlap_months,
            ).splice(national.loc[:link_end, component].astype(float), monthly)
            linked = splice.values.reindex(self._months)  # noqa: PD011
            if (
                linked.isna().any()
                or not np.isfinite(np.array(linked, dtype=float)).all()
            ):
                raise ReconstructionError(
                    f"Incomplete splice: {name}/{component}"
                )
            result[component] = linked
            rho = None if fit.rho is None else float(fit.rho.value)
            records.append(
                {
                    "dep_code": code,
                    "department": name,
                    "quantity": component,
                    "method": policy.method,
                    "national_indicator": component,
                    "rho": rho,
                    "rho_at_bound": False
                    if fit.rho is None
                    else bool(fit.rho.at_bound),
                    "warnings": " | ".join(fit.diagnostics.warnings),
                    "max_annual_anchor_error_persons": float(
                        errors.abs().max()
                    ),
                    "link_ratio": float(splice.link["ratio"]),
                    "negative_month_count": int((linked < 0).sum()),
                    "min_value_persons": float(linked.min()),
                }
            )
        result["labor_force"] = result["employed"] + result["unemployed"]
        result["working_age"] = result["labor_force"] + result["inactive"]
        first_anchor = pd.Period(policy.anchor_start_period, freq="M")
        frame = result.reset_index(drop=True)
        frame.insert(
            0,
            "origin",
            np.where(
                self._months < first_anchor, ORIGIN_BACKCAST, ORIGIN_ANCHORED
            ),
        )
        frame.insert(0, "year", self._months.year)
        frame.insert(0, "period", self._months.astype(str))
        frame.insert(0, "department", name)
        frame.insert(0, "dep_code", code)
        return frame, records
