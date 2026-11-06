"""Synthetic urban signal for Cundinamarca (code 25).

Cundinamarca has no GEIH urban domain. Its modeling signal uses Bogotá
(code 11) only as the temporal pattern, scaled to Cundinamarca's own
departmental anchors over the calibration years with a ratio splice. The
annual path is made coherent, given monthly profiles from the national
homologous series, and extended to 1993 by a monthly ratio splice. It is a
predictor for the departmental model, never an observed DANE value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from tempdisagg import SeriesSplicer

from icml.urban.accounting import URBAN_SIGNALS, project_signals
from icml.urban.inputs import anchor_column, geih_column

ORIGIN_EARLY = "1993_2006_NACIONAL_HOMOLOGO"
ORIGIN_DONOR = "2007_2020_BOGOTA_DONANTE_ESCALADO"
ORIGIN_ANCHORED = "2021_2024_ANCLA_DEPARTAMENTAL_CON_PERFIL_MENSUAL_INFERIDO"
ANNUAL_ORIGIN_ANCHORED = "ANCLA_OFICIAL_DEPARTAMENTAL_2021_2024_CONCILIADA"
ANNUAL_ORIGIN_ESTIMATED = "ESTIMADO_BOGOTA_PATRON_ESCALADO"
UNIT_TYPE = "URBANA_SINTETICA_PARA_MODELO_DEPARTAMENTAL"
_RATIO_TOLERANCE = 1e-12
_CLONE_TOLERANCE = 1e-9
_ANCHOR_TOLERANCE = 1e-5
_IDENTITY_TOLERANCE = 1e-6


class SyntheticSignalError(ValueError):
    """Raised when the synthetic signal violates its frozen contract."""


@dataclass(frozen=True)
class SyntheticSignalPolicy:
    """Identity, calendar and limits of the synthetic signal."""

    recipient_code: int
    donor_code: int
    recipient_name: str
    donor_name: str
    calibration_years: Sequence[int]
    first_year: int
    last_year: int
    max_official_anchor_adjustment_persons: float

    @property
    def years(self) -> list[int]:
        """Return the annual span of the signal."""
        return list(range(self.first_year, self.last_year + 1))


@dataclass(frozen=True)
class SyntheticSignalResult:
    """Monthly and annual synthetic signal with its audit tables."""

    monthly: pd.DataFrame
    annual: pd.DataFrame
    calibration: pd.DataFrame
    monthly_links: pd.DataFrame
    unreconciled: pd.DataFrame
    official_anchors: pd.DataFrame


class SyntheticSignalBuilder:
    """Build the frozen synthetic signal for one recipient."""

    def __init__(
        self,
        policy: SyntheticSignalPolicy,
        frozen_donor: Mapping[str, Any],
        published_unit_persons: float,
    ) -> None:
        """Validate the frozen donor record against the policy.

        Raises
        ------
        SyntheticSignalError
            If the frozen record does not describe the same calibration.
        """
        if (
            frozen_donor["recipient_code"] != policy.recipient_code
            or frozen_donor["donor_code"] != policy.donor_code
            or list(frozen_donor["calibration_years"])
            != list(policy.calibration_years)
        ):
            raise SyntheticSignalError("Frozen donor record does not match")
        self._policy = policy
        self._frozen = frozen_donor
        self._unit = published_unit_persons

    def _inputs(
        self, historical: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        policy = self._policy
        recipient = historical[
            historical["dep_code"] == policy.recipient_code
        ].sort_values("year")
        donor = historical[
            historical["dep_code"] == policy.donor_code
        ].sort_values("year")
        if len(recipient) != len(donor) or recipient.empty:
            raise SyntheticSignalError("Incomplete recipient/donor history")
        if not recipient["dep_code_similar"].eq(policy.donor_code).all():
            raise SyntheticSignalError("History does not use the donor")
        anchored_years = set(
            recipient.loc[recipient["employed"].notna(), "year"]
        )
        if anchored_years != set(policy.calibration_years):
            raise SyntheticSignalError("Anchor years differ from policy")
        for quantity in URBAN_SIGNALS:
            difference = np.array(
                recipient[geih_column(quantity)], dtype=float
            ) - np.array(donor[geih_column(quantity)], dtype=float)
            if not np.allclose(difference, 0, rtol=0, atol=_CLONE_TOLERANCE):
                raise SyntheticSignalError(f"Donor clone mismatch: {quantity}")
        return recipient.set_index("year"), donor

    def build(
        self, historical: pd.DataFrame, national: pd.DataFrame
    ) -> SyntheticSignalResult:
        """Build the signal from the historical table and national months.

        ``national`` must cover January of the first retropolated year to
        December of ``last_year`` with canonical quantity columns.
        """
        policy = self._policy
        recipient, _ = self._inputs(historical)
        years = policy.years
        calibration = list(policy.calibration_years)
        raw_annual = pd.DataFrame(
            index=pd.Index(years, name="year"),
            columns=list(URBAN_SIGNALS),
            dtype=float,
        )
        official = pd.DataFrame(
            index=pd.Index(calibration, name="year"),
            columns=list(URBAN_SIGNALS),
            dtype=float,
        )
        factors = []
        for quantity in URBAN_SIGNALS:
            donor_series = pd.Series(
                np.array(
                    recipient.loc[years, geih_column(quantity)], dtype=float
                )
                * self._unit,
                index=pd.PeriodIndex([str(y) for y in years], freq="Y"),
            )
            targets = pd.Series(
                np.array(
                    recipient.loc[calibration, anchor_column(quantity)],
                    dtype=float,
                ),
                index=pd.PeriodIndex([str(y) for y in calibration], freq="Y"),
            )
            if (donor_series <= 0).any() or (targets <= 0).any():
                raise SyntheticSignalError("Non-positive donor or anchors")
            splice = SeriesSplicer(
                method="ratio", overlap_periods=len(calibration)
            ).splice(donor_series, targets)
            ratio = float(splice.link["ratio"])
            expected = float(
                targets.sum() / donor_series.loc[targets.index].sum()
            )
            frozen = float(
                self._frozen["ratio_by_variable"][anchor_column(quantity)]
            )
            if not np.isclose(
                ratio, expected, atol=_RATIO_TOLERANCE, rtol=_RATIO_TOLERANCE
            ):
                raise SyntheticSignalError("Splice ratio mismatch")
            if not np.isclose(
                ratio, frozen, atol=_RATIO_TOLERANCE, rtol=_RATIO_TOLERANCE
            ):
                raise SyntheticSignalError(
                    f"Frozen ratio changed for {quantity}: a new "
                    "methodological version is required"
                )
            raw_annual[quantity] = np.array(
                splice.values,  # noqa: PD011
                dtype=float,
            )
            official[quantity] = np.array(targets, dtype=float)
            donor_calibration = np.array(donor_series.loc[targets.index])
            factors.append(
                {
                    "quantity": quantity,
                    "donor_code": policy.donor_code,
                    "donor_name": policy.donor_name,
                    "recipient_code": policy.recipient_code,
                    "recipient_name": policy.recipient_name,
                    "calibration_start": calibration[0],
                    "calibration_end": calibration[-1],
                    "ratio": ratio,
                    "donor_mean": float(donor_calibration.mean()),
                    "recipient_official_mean": float(targets.mean()),
                    "max_ratio_variation_pct": float(
                        np.max(
                            np.abs(
                                np.array(targets) / donor_calibration / ratio
                                - 1
                            )
                        )
                        * 100
                    ),
                }
            )

        reference = np.array(raw_annual.loc[years[0]], dtype=float)
        annual = pd.DataFrame(
            project_signals(np.array(raw_annual), reference),
            index=raw_annual.index,
            columns=list(URBAN_SIGNALS),
        )
        adjustment = float(
            np.abs(np.array(annual.loc[calibration] - official)).max()
        )
        if adjustment > policy.max_official_anchor_adjustment_persons:
            raise SyntheticSignalError(
                f"Reconciliation would alter official anchors: {adjustment}"
            )

        months = self._months(national)
        nat = self._national(national, months)
        monthly = pd.DataFrame(
            index=months, columns=list(URBAN_SIGNALS), dtype=float
        )
        raw_monthly = monthly.copy()
        for year in years:
            reference_months = np.array(nat.loc[str(year)], dtype=float)
            target = np.array(annual.loc[year], dtype=float)
            scaled = reference_months * (
                target / reference_months.mean(axis=0)
            )
            corrected = project_signals(scaled, target)
            if not np.allclose(
                corrected.mean(axis=0), target, atol=_ANCHOR_TOLERANCE, rtol=0
            ):
                raise SyntheticSignalError(f"Annual anchor lost: {year}")
            monthly.loc[str(year)] = corrected
            raw_monthly.loc[str(year)] = scaled

        first_anchor = str(years[0])
        before = months[months.year < years[0]]
        links = []
        for quantity in URBAN_SIGNALS:
            splice = SeriesSplicer(method="ratio", overlap_periods=12).splice(
                nat.loc[: f"{first_anchor}-12", quantity],
                raw_monthly.loc[f"{first_anchor}-01" :, quantity],
            )
            linked = splice.values  # noqa: PD011 (tempdisagg result)
            raw_monthly.loc[before, quantity] = np.array(
                linked.loc[before], dtype=float
            )
            links.append(
                {
                    "quantity": quantity,
                    "indicator": f"national_{quantity}",
                    "ratio": float(splice.link["ratio"]),
                    "link_year": years[0],
                }
            )
        monthly.loc[before] = project_signals(
            np.array(raw_monthly.loc[before], dtype=float),
            np.array(annual.loc[years[0]], dtype=float),
        )
        self._verify(monthly, annual, years)
        return self._tables(
            monthly, raw_monthly, annual, raw_annual, official, factors, links
        )

    def _months(self, national: pd.DataFrame) -> pd.PeriodIndex:
        first = str(national["period"].astype(str).min())
        return pd.period_range(first, f"{self._policy.last_year}-12", freq="M")

    @staticmethod
    def _national(
        national: pd.DataFrame, months: pd.PeriodIndex
    ) -> pd.DataFrame:
        data = national.copy()
        data.index = pd.PeriodIndex(data["period"].astype(str), freq="M")
        data = data.loc[months[0] : months[-1], list(URBAN_SIGNALS)]
        if not data.index.equals(months) or data.isna().any().any():
            raise SyntheticSignalError("National months are incomplete")
        return data

    @staticmethod
    def _verify(
        monthly: pd.DataFrame, annual: pd.DataFrame, years: Sequence[int]
    ) -> None:
        if (
            monthly.isna().any().any()
            or (monthly <= 0).any().any()
            or (
                monthly["working_age"]
                > monthly["population"] + _IDENTITY_TOLERANCE
            ).any()
        ):
            raise SyntheticSignalError("Inadmissible synthetic values")
        if not np.allclose(
            monthly["labor_force"],
            monthly["employed"] + monthly["unemployed"],
            atol=_IDENTITY_TOLERANCE,
            rtol=0,
        ):
            raise SyntheticSignalError("Labor force identity broken")
        if not np.allclose(
            monthly["working_age"],
            monthly["labor_force"] + monthly["inactive"],
            atol=_IDENTITY_TOLERANCE,
            rtol=0,
        ):
            raise SyntheticSignalError("Working-age identity broken")
        for year in years:
            if not np.allclose(
                np.array(monthly.loc[str(year)].mean()),
                np.array(annual.loc[year]),
                atol=_ANCHOR_TOLERANCE,
                rtol=0,
            ):
                raise SyntheticSignalError(f"Year {year} not reproduced")

    def _tables(
        self,
        monthly: pd.DataFrame,
        raw_monthly: pd.DataFrame,
        annual: pd.DataFrame,
        raw_annual: pd.DataFrame,
        official: pd.DataFrame,
        factors: list[dict[str, Any]],
        links: list[dict[str, Any]],
    ) -> SyntheticSignalResult:
        policy = self._policy
        calibration = set(policy.calibration_years)
        annual_table = annual.reset_index()
        annual_table["origin"] = np.where(
            annual_table["year"].isin(calibration),
            ANNUAL_ORIGIN_ANCHORED,
            ANNUAL_ORIGIN_ESTIMATED,
        )
        for quantity in URBAN_SIGNALS:
            annual_table[f"raw_{quantity}"] = np.array(raw_annual[quantity])
        periods = monthly.index.astype(str)
        first_calibration = f"{min(calibration)}-01"
        origin = np.select(
            [periods < f"{policy.first_year}-01", periods < first_calibration],
            [ORIGIN_EARLY, ORIGIN_DONOR],
            default=ORIGIN_ANCHORED,
        )
        monthly_table = monthly.reset_index(drop=True)
        monthly_table.insert(0, "period", periods)
        monthly_table.insert(0, "city_name", policy.recipient_name)
        monthly_table.insert(0, "city_code", policy.recipient_code)
        monthly_table["unit_type"] = UNIT_TYPE
        monthly_table["origin"] = origin
        raw_table = raw_monthly.reset_index(drop=True)
        raw_table.insert(0, "period", periods)
        raw_table.insert(0, "city_code", policy.recipient_code)
        return SyntheticSignalResult(
            monthly=monthly_table,
            annual=annual_table,
            calibration=pd.DataFrame(factors),
            monthly_links=pd.DataFrame(links),
            unreconciled=raw_table,
            official_anchors=official.reset_index(),
        )
