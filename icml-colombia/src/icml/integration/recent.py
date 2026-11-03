"""Urban panel 1993 to the last published month (33 signals x months).

Extends the propagated 1993-2020 urban signals with latent months inferred
from the rolling windows (32 cities) and, for the synthetic Cundinamarca
signal, with Bogotá's latent path rescaled to Cundinamarca's own annual
departmental anchors. Approved months up to 2020 are never modified.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.integration.windows import (
    FIT_COMPONENTS,
    LatentWindowFit,
    WindowFitPolicy,
    rolling_means,
)
from icml.urban.accounting import URBAN_SIGNALS

ORIGIN_LATENT = "GEIH_32_CIUDADES_LATENTE_RESTRICCIONES_VENTANAS_12M"
ORIGIN_LATENT_PROVISIONAL = "GEIH_32_CIUDADES_LATENTE_PROVISIONAL_2026"
ORIGIN_SYNTHETIC = "CUNDINAMARCA_SINTETICA_BOGOTA_PATRON_ANCLAS_PROPIAS"
ORIGIN_SYNTHETIC_PROVISIONAL = "CUNDINAMARCA_SINTETICA_PROVISIONAL_2026"
CITY_UNIT = "CIUDAD_O_AREA_METROPOLITANA"
SYNTHETIC_UNIT = "URBANA_SINTETICA_PARA_MODELO_DEPARTAMENTAL"
_IDENTITY_TOLERANCE = 1e-5
_POPULATION_TOLERANCE = 1e-4
_NEGATIVE_TOLERANCE = 1e-6


class RecentPanelError(ValueError):
    """Raised when the recent urban panel breaks its contract."""


@dataclass(frozen=True)
class SyntheticExtensionPolicy:
    """How the synthetic signal is extended after 2020."""

    recipient_code: int
    donor_code: int
    recipient_name: str
    anchor_first_year: int
    anchor_last_year: int


@dataclass(frozen=True)
class RecentPanelResult:
    """Full panel, latent segment and audit tables."""

    panel: pd.DataFrame
    latent: pd.DataFrame
    window_control: pd.DataFrame
    window_comparison: pd.DataFrame
    synthetic_anchors: pd.DataFrame


def _with_derived(values: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    values["labor_force"] = values["employed"] + values["unemployed"]
    values["working_age"] = values["labor_force"] + values["inactive"]
    return values


class RecentUrbanPanelBuilder:
    """Build the recent latent segment and append it to the history."""

    def __init__(
        self,
        fit_policy: WindowFitPolicy,
        synthetic: SyntheticExtensionPolicy,
        city_names: Mapping[int, str],
    ) -> None:
        """Compose the latent fit with the synthetic extension policy."""
        self._fit = LatentWindowFit(fit_policy)
        self._months = fit_policy.months()
        self._synthetic = synthetic
        self._codes = {name: code for code, name in city_names.items()}

    def build(
        self,
        history: pd.DataFrame,
        windows: Mapping[str, Mapping[str, np.ndarray]],
        national: pd.DataFrame,
        departmental: pd.DataFrame,
    ) -> RecentPanelResult:
        """Return the extended panel and its audits.

        Raises
        ------
        RecentPanelError
            If windows do not match the catalog, coverage is incomplete or
            approved months change.
        """
        if set(windows) != set(self._codes):
            raise RecentPanelError(
                "Window cities differ from the catalog: "
                f"{sorted(set(windows) ^ set(self._codes))}"
            )
        reference = national.set_index("period")
        months = list(self._months.astype(str))
        previous_month = str(self._months[0] - 1)
        national_recent = reference.loc[months]
        national_previous = reference.loc[previous_month]
        previous = history[history["period"] == previous_month].set_index(
            "city_code"
        )
        latent_rows: list[dict[str, Any]] = []
        control: list[dict[str, Any]] = []
        comparison: list[dict[str, Any]] = []
        window_ends = list((self._months[11:]).astype(str))
        for name, city_windows in windows.items():
            code = self._codes[name]
            values: dict[str, np.ndarray] = {}
            diagnostics: dict[str, dict[str, Any]] = {}
            for component in FIT_COMPONENTS:
                values[component], diagnostics[component] = self._fit.fit(
                    np.asarray(city_windows[component], dtype=float),
                    np.array(national_recent[component], dtype=float),
                    float(previous.loc[code, component]),
                    float(national_previous[component]),
                )
            values = _with_derived(values)
            internal = {
                "labor_force": float(
                    np.max(
                        np.abs(
                            city_windows["labor_force"]
                            - city_windows["employed"]
                            - city_windows["unemployed"]
                        )
                    )
                ),
                "working_age": float(
                    np.max(
                        np.abs(
                            city_windows["working_age"]
                            - city_windows["labor_force"]
                            - city_windows["inactive"]
                        )
                    )
                ),
            }
            for quantity in URBAN_SIGNALS:
                estimated = rolling_means(values[quantity])
                observed = np.asarray(city_windows[quantity], dtype=float)
                for end, obs, est in zip(
                    window_ends, observed, estimated, strict=True
                ):
                    comparison.append(
                        {
                            "city_code": code,
                            "city_name": name,
                            "window_end": end,
                            "quantity": quantity,
                            "published_mean": obs,
                            "estimated_mean": est,
                            "difference_persons": est - obs,
                        }
                    )
                fit = diagnostics.get(quantity, {})
                control.append(
                    {
                        "city_code": code,
                        "city_name": name,
                        "quantity": quantity,
                        "max_window_error_persons": float(
                            np.max(np.abs(observed - estimated))
                        ),
                        "published_labor_force_identity": internal[
                            "labor_force"
                        ],
                        "published_working_age_identity": internal[
                            "working_age"
                        ],
                        "seam_log_pct": float(
                            100
                            * np.log(
                                values[quantity][0]
                                / float(previous.loc[code, quantity])
                            )
                        ),
                        "first_year_ratio_to_national": float(
                            np.mean(values[quantity][:12])
                            / float(
                                np.mean(
                                    np.array(
                                        national_recent[quantity], dtype=float
                                    )[:12]
                                )
                            )
                        ),
                        "prior_wape_pct": fit.get("prior_wape_pct"),
                        "lower_bound_active": fit.get(
                            "lower_bound_active", False
                        ),
                    }
                )
            latent_rows.extend(
                self._rows(
                    code,
                    name,
                    values,
                    CITY_UNIT,
                    ORIGIN_LATENT,
                    ORIGIN_LATENT_PROVISIONAL,
                )
            )
        latent = pd.DataFrame(latent_rows)
        synthetic, anchors = self._synthetic_extension(latent, departmental)
        latent = pd.concat([latent, synthetic], ignore_index=True)
        panel = (
            pd.concat([history, latent], ignore_index=True)
            .sort_values(["city_code", "period"])
            .reset_index(drop=True)
        )
        self._verify(panel, history)
        return RecentPanelResult(
            panel=panel,
            latent=latent,
            window_control=pd.DataFrame(control),
            window_comparison=pd.DataFrame(comparison),
            synthetic_anchors=anchors,
        )

    def _rows(
        self,
        code: int,
        name: str,
        values: Mapping[str, np.ndarray],
        unit: str,
        origin: str,
        provisional: str,
    ) -> list[dict[str, Any]]:
        last_year = self._months[-1].year
        return [
            {
                "city_code": code,
                "city_name": name,
                "period": str(period),
                "origin": provisional if period.year == last_year else origin,
                "unit_type": unit,
                **{q: float(values[q][t]) for q in URBAN_SIGNALS},
            }
            for t, period in enumerate(self._months)
        ]

    def _synthetic_extension(
        self, latent: pd.DataFrame, departmental: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        policy = self._synthetic
        months = list(self._months.astype(str))
        donor = (
            latent[latent["city_code"] == policy.donor_code]
            .set_index("period")
            .loc[months]
        )
        recipient = departmental[
            departmental["dep_code"] == policy.recipient_code
        ].copy()
        recipient["year"] = recipient["period"].str.slice(0, 4).astype(int)
        anchors = recipient.groupby("year")[list(FIT_COMPONENTS)].mean()
        years = list(
            range(policy.anchor_first_year, policy.anchor_last_year + 1)
        )
        missing = set(years) - set(anchors.index)
        if missing:
            raise RecentPanelError(f"Missing synthetic anchors: {missing}")
        donor_years = donor.index.str.slice(0, 4).astype(int)
        values: dict[str, np.ndarray] = {}
        for component in FIT_COMPONENTS:
            ratios = {
                year: float(
                    anchors.loc[year, component]
                    / donor.loc[donor_years == year, component].mean()
                )
                for year in years
            }
            values[component] = np.array(
                [
                    float(donor.iloc[t][component])
                    * ratios.get(period.year, ratios[policy.anchor_last_year])
                    for t, period in enumerate(self._months)
                ]
            )
        values = _with_derived(values)
        trace = []
        for quantity in URBAN_SIGNALS:
            for year in years:
                direct = recipient.loc[
                    recipient["year"] == year, quantity
                ].mean()
                produced = float(
                    np.mean(
                        values[quantity][
                            np.array([p.year == year for p in self._months])
                        ]
                    )
                )
                trace.append(
                    {
                        "city_code": policy.recipient_code,
                        "year": year,
                        "quantity": quantity,
                        "departmental_anchor": direct,
                        "synthetic_mean": produced,
                        "difference_persons": produced - direct,
                    }
                )
        rows = pd.DataFrame(
            self._rows(
                policy.recipient_code,
                policy.recipient_name,
                values,
                SYNTHETIC_UNIT,
                ORIGIN_SYNTHETIC,
                ORIGIN_SYNTHETIC_PROVISIONAL,
            )
        )
        return rows, pd.DataFrame(trace)

    def _verify(self, panel: pd.DataFrame, history: pd.DataFrame) -> None:
        sizes = panel.groupby("city_code").size()
        if (sizes != sizes.iloc[0]).any() or panel.duplicated(
            subset=["city_code", "period"]
        ).any():
            raise RecentPanelError("Incomplete 33-signal panel")
        values = panel[list(URBAN_SIGNALS)]
        if (
            values.isna().any().any()
            or values.min().min() < -_NEGATIVE_TOLERANCE
        ):
            raise RecentPanelError("Missing or negative values")
        if (
            panel["working_age"] > panel["population"] + _POPULATION_TOLERANCE
        ).any():
            raise RecentPanelError("Working age above population")
        if (
            max(
                float(
                    (
                        panel["labor_force"]
                        - panel["employed"]
                        - panel["unemployed"]
                    )
                    .abs()
                    .max()
                ),
                float(
                    (
                        panel["working_age"]
                        - panel["labor_force"]
                        - panel["inactive"]
                    )
                    .abs()
                    .max()
                ),
            )
            > _IDENTITY_TOLERANCE
        ):
            raise RecentPanelError("Identities not closed")
        keys = ["city_code", "period"]
        approved = panel[panel["period"] <= history["period"].max()]
        if (
            not approved.sort_values(keys)[list(URBAN_SIGNALS)]
            .reset_index(drop=True)
            .equals(
                history.sort_values(keys)[list(URBAN_SIGNALS)].reset_index(
                    drop=True
                )
            )
        ):
            raise RecentPanelError("Approved history was modified")


def predictor_base(
    panel: pd.DataFrame,
    projections: pd.DataFrame,
    anchored_codes: Sequence[int],
    anchored_years: range,
) -> pd.DataFrame:
    """Add demographic projections, urban rates and target flags.

    Raises
    ------
    RecentPanelError
        If a territory-year lacks a projection.
    """
    base = panel.copy()
    base["year"] = base["period"].str.slice(0, 4).astype(int)
    base = base.merge(
        projections[["dep_code", "year", "population_demographic_projection"]],
        left_on=["city_code", "year"],
        right_on=["dep_code", "year"],
        how="left",
        validate="many_to_one",
    ).drop(columns=["dep_code"])
    if base["population_demographic_projection"].isna().any():
        raise RecentPanelError("Missing demographic projection")
    return with_urban_rates(base).assign(
        target_with_annual_anchor=lambda d: (
            d["city_code"].isin(list(anchored_codes))
            & d["year"].between(anchored_years.start, anchored_years.stop - 1)
        ),
        is_synthetic_signal=lambda d: d["unit_type"] == SYNTHETIC_UNIT,
    )


def with_urban_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Recompute the urban signal rates (percent) from levels."""
    result = frame.copy()
    result["unemployment_rate_signal"] = (
        100 * result["unemployed"] / result["labor_force"]
    )
    result["employment_rate_signal"] = (
        100 * result["employed"] / result["working_age"]
    )
    result["participation_rate_signal"] = (
        100 * result["labor_force"] / result["working_age"]
    )
    return result
