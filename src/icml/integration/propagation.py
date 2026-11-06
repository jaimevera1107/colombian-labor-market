"""Propagation of the national seasonal adjustment to territorial series.

The national 1993-2000 months gained a seasonal pattern after the urban and
departmental series had been built from the previous (reconciled) national
series. This stage rebuilds, deterministically, only the segment whose
single input changed: the frozen urban and departmental link factors are
reapplied to the seasonal national series. Nothing is re-estimated, months
from 2001 onward are kept bit-for-bit and annual means do not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.urban.accounting import URBAN_SIGNALS, project_signals

ORIGIN_NATIONAL_SEASONAL = "RECONSTRUIDO_ESTACIONAL_063"
ORIGIN_NATIONAL_OBSERVED = "geih_observado"
ORIGIN_URBAN_SEASONAL = "1993_2000_RETROPOLACION_NACIONAL_ESTACIONAL_063"
ORIGIN_DEPARTMENTAL_SEASONAL = (
    "INFERIDO_NACIONAL_ESTACIONAL_063_SIN_ANCLA_DEPARTAMENTAL"
)
DEPARTMENTAL_COMPONENTS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
)
_TRACE_TOLERANCE = 1e-5
_ANNUAL_TOLERANCE = 1e-4
_IDENTITY_TOLERANCE = 1e-5
_POST_HISTORY_TOLERANCE = 1e-6


class PropagationError(ValueError):
    """Raised when the propagation would alter protected values."""


@dataclass(frozen=True)
class PropagationPolicy:
    """Calendar of the propagation."""

    history_start: str
    history_end: str
    anchor_year: int
    overlap_end: str

    def history_periods(self) -> list[str]:
        """Return the months whose national input changed."""
        return list(
            pd.period_range(
                self.history_start, self.history_end, freq="M"
            ).astype(str)
        )


@dataclass(frozen=True)
class PropagationResult:
    """Propagated series and audit tables."""

    national: pd.DataFrame
    urban: pd.DataFrame
    departmental: pd.DataFrame
    urban_changes: pd.DataFrame
    departmental_changes: pd.DataFrame
    signal_transfer: pd.DataFrame


def _indexed(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.set_index("period")


def _annual_gap(before: pd.DataFrame, after: pd.DataFrame, key: str) -> float:
    """Largest change of a unit-year mean between two panels."""

    def means(frame: pd.DataFrame) -> pd.DataFrame:
        years = frame["period"].str.slice(0, 4)
        return frame.groupby([frame[key], years])[list(URBAN_SIGNALS)].mean()

    return float(
        np.max(np.abs(np.array(means(after) - means(before), dtype=float)))
    )


class SeasonalPropagation:
    """Reapply frozen link factors to the seasonal national series."""

    def __init__(self, policy: PropagationPolicy) -> None:
        """Store the policy."""
        self._policy = policy
        self._history = policy.history_periods()

    def national(
        self,
        combined: pd.DataFrame,
        reconciled: pd.DataFrame,
        seasonal: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Return the full national series and the old/new history.

        Raises
        ------
        PropagationError
            If the seasonal series changed post-history months or annual
            means.
        """
        history = self._history
        old = _indexed(reconciled)
        new = _indexed(seasonal)
        first_after = str(pd.Period(self._policy.history_end, freq="M") + 1)
        overlap = slice(first_after, self._policy.overlap_end)
        if not np.allclose(
            np.array(new.loc[overlap, list(URBAN_SIGNALS)]),
            np.array(old.loc[overlap, list(URBAN_SIGNALS)]),
            atol=_POST_HISTORY_TOLERANCE,
            rtol=0,
        ):
            raise PropagationError("Seasonal series changed observed months")
        national = _indexed(combined).copy()
        national.loc[history, list(URBAN_SIGNALS)] = np.array(
            new.loc[history, list(URBAN_SIGNALS)], dtype=float
        )
        national["origin"] = np.where(
            national.index.isin(history),
            ORIGIN_NATIONAL_SEASONAL,
            ORIGIN_NATIONAL_OBSERVED,
        )
        values = national[list(URBAN_SIGNALS)]
        if values.isna().any().any() or (values <= 0).any().any():
            raise PropagationError("Invalid national series")
        years = pd.Index([p[:4] for p in history])
        before = old.loc[history, list(URBAN_SIGNALS)]
        after = national.loc[history, list(URBAN_SIGNALS)]
        gap = float(
            np.abs(
                np.array(
                    after.groupby(years).mean() - before.groupby(years).mean()
                )
            ).max()
        )
        if gap > _ANNUAL_TOLERANCE:
            raise PropagationError(f"Seasonality altered annual means: {gap}")
        table = national.reset_index()[["period", "origin", *URBAN_SIGNALS]]
        return table, before, after

    def urban(
        self,
        signals: pd.DataFrame,
        links: pd.DataFrame,
        synthetic_links: pd.DataFrame,
        unreconciled: pd.DataFrame,
        synthetic_unreconciled: pd.DataFrame,
        national_old: pd.DataFrame,
        national_new: pd.DataFrame,
        synthetic_code: int,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
        """Rebuild the urban 1993-2000 segment with frozen link factors."""
        history = self._history
        anchor = (
            f"{self._policy.anchor_year}-01",
            f"{self._policy.anchor_year}-12",
        )
        result = signals.copy()
        changes, transfer = [], []
        for code, group in signals.groupby("city_code", sort=True):
            code = int(code)
            index = (
                group[group["period"].isin(history)]
                .sort_values("period")
                .index
            )
            if len(index) != len(history):
                raise PropagationError(f"Incomplete urban history: {code}")
            if code == synthetic_code:
                factor = synthetic_links.set_index("quantity")["ratio"]
                source = synthetic_unreconciled
            else:
                factor = links[links["city_code"] == code].set_index(
                    "quantity"
                )["link_factor"]
                source = unreconciled[unreconciled["city_code"] == code]
            coefficients = np.array(
                factor.loc[list(URBAN_SIGNALS)], dtype=float
            )
            past = np.array(
                source.set_index("period").loc[history, list(URBAN_SIGNALS)],
                dtype=float,
            )
            reproduced = (
                np.array(national_old, dtype=float) * coefficients[None, :]
            )
            trace_error = float(np.max(np.abs(past - reproduced)))
            if trace_error > _TRACE_TOLERANCE:
                raise PropagationError(
                    f"Urban source does not match frozen factor: {code}"
                )
            before = np.array(
                result.loc[index, list(URBAN_SIGNALS)], dtype=float
            )
            raw = np.array(national_new, dtype=float) * coefficients[None, :]
            in_anchor = (result["city_code"] == code) & result[
                "period"
            ].between(*anchor)
            reference = np.array(
                result.loc[in_anchor, list(URBAN_SIGNALS)].mean(), dtype=float
            )
            after = project_signals(raw, reference)
            if not (np.isfinite(after).all() and (after > 0).all()):
                raise PropagationError(f"Invalid urban closure: {code}")
            result.loc[index, list(URBAN_SIGNALS)] = after
            result.loc[index, "origin"] = ORIGIN_URBAN_SEASONAL
            changes.append(
                {
                    "city_code": code,
                    "city_name": str(group["city_name"].iloc[0]),
                    "unit": "synthetic" if code == synthetic_code else "city",
                    "max_monthly_change_pct": float(
                        np.max(np.abs(after / before - 1)) * 100
                    ),
                    "trace_error_persons": trace_error,
                    "max_change_persons": float(
                        np.max(np.abs(after - before))
                    ),
                }
            )
            for position, quantity in enumerate(URBAN_SIGNALS):
                transfer.append(
                    {
                        "city_code": code,
                        "quantity": quantity,
                        "frozen_factor": float(coefficients[position]),
                        "max_monthly_change_pct": float(
                            np.max(
                                np.abs(
                                    after[:, position] / before[:, position]
                                    - 1
                                )
                            )
                            * 100
                        ),
                    }
                )
        self._protect(signals, result, "city_code", "urban")
        return result, changes, transfer

    def departmental(
        self,
        panel: pd.DataFrame,
        diagnostics: pd.DataFrame,
        national_old: pd.DataFrame,
        national_new: pd.DataFrame,
    ) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
        """Rebuild the departmental 1993-2000 labor components.

        Population keeps its independent demographic backcast.
        """
        history = self._history
        result = panel.copy()
        changes = []
        for code, group in panel.groupby("dep_code", sort=True):
            index = (
                group[group["period"].isin(history)]
                .sort_values("period")
                .index
            )
            links = diagnostics[diagnostics["dep_code"] == code].set_index(
                "quantity"
            )
            before = np.array(
                result.loc[index, list(DEPARTMENTAL_COMPONENTS)], dtype=float
            )
            fresh = np.zeros_like(before)
            for position, component in enumerate(DEPARTMENTAL_COMPONENTS):
                ratio = float(links.loc[component, "link_ratio"])
                baseline = (
                    np.array(national_old[component], dtype=float) * ratio
                )
                if (
                    np.max(np.abs(baseline - before[:, position]))
                    > _TRACE_TOLERANCE
                ):
                    raise PropagationError(
                        f"Departmental link not reproduced: {code}"
                    )
                fresh[:, position] = (
                    np.array(national_new[component], dtype=float) * ratio
                )
            result.loc[index, list(DEPARTMENTAL_COMPONENTS)] = fresh
            result.loc[index, "labor_force"] = fresh[:, 0] + fresh[:, 1]
            result.loc[index, "working_age"] = fresh.sum(axis=1)
            result.loc[index, "origin"] = ORIGIN_DEPARTMENTAL_SEASONAL
            population = np.array(result.loc[index, "population"], dtype=float)
            if np.any(fresh.sum(axis=1) > population + 1e-6):
                raise PropagationError(f"Working age above population {code}")
            changes.append(
                {
                    "dep_code": int(code),
                    "department": str(group["department"].iloc[0]),
                    "max_component_change_pct": float(
                        np.max(np.abs(fresh / before - 1)) * 100
                    ),
                    "max_change_persons": float(
                        np.max(np.abs(fresh - before))
                    ),
                }
            )
        self._protect(panel, result, "dep_code", "departmental")
        if not np.array_equal(
            np.array(result["population"]), np.array(panel["population"])
        ):
            raise PropagationError("Departmental population changed")
        return result, changes

    def _protect(
        self, before: pd.DataFrame, after: pd.DataFrame, key: str, name: str
    ) -> None:
        outside = ~before["period"].isin(self._history)
        if not np.array_equal(
            np.array(after.loc[outside, list(URBAN_SIGNALS)]),
            np.array(before.loc[outside, list(URBAN_SIGNALS)]),
        ):
            raise PropagationError(f"{name}: months outside history changed")
        history = before["period"].isin(self._history)
        gap = _annual_gap(before.loc[history], after.loc[history], key)
        if gap > _ANNUAL_TOLERANCE:
            raise PropagationError(f"{name}: annual means changed by {gap}")
        identity = max(
            float(
                (
                    after["labor_force"]
                    - after["employed"]
                    - after["unemployed"]
                )
                .abs()
                .max()
            ),
            float(
                (
                    after["working_age"]
                    - after["labor_force"]
                    - after["inactive"]
                )
                .abs()
                .max()
            ),
        )
        if identity > _IDENTITY_TOLERANCE:
            raise PropagationError(f"{name}: identities not closed")
