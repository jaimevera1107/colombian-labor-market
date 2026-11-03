"""Monthly urban signals for the 32 cities, January 1993 to December 2020.

For 2007-2020 each city has an annual anchor (GEIH for 23 cities, the
closed donor reconstruction for nine). The monthly profile of each year is
the national homologous series rescaled to the anchor and projected onto
the accounting subspace. Before 2007 the national series is linked to the
2007 level with a ratio splice (``tempdisagg`` ``SeriesSplicer``) and
projected with the 2007 anchor weights. These are modeling signals, not
observed GEIH monthly data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from tempdisagg import SeriesSplicer

from icml.urban.accounting import URBAN_SIGNALS, project_signals

ORIGIN_RETROPOLATED = "1993_2006_RETROPOLACION_NACIONAL"
ORIGIN_DONOR_ANCHOR = "2007_2020_ANCLA_URBANA_DONANTE"
ORIGIN_GEIH_ANCHOR = "2007_2020_GEIH_URBANA_ANUAL"
ANCHOR_GEIH = "GEIH_23_CIUDADES_REFERENCIA_HISTORICA_MILES"
ANCHOR_DONOR = "RETROPOLADO_DONANTE_PARETO_CIERRE_A"
_SPLICE_RELATIVE_TOLERANCE = 1e-9
_SPLICE_ABSOLUTE_TOLERANCE = 1e-12
_LINK_TOLERANCE = 1e-7
_IDENTITY_TOLERANCE = 1e-6
_RATIO_SIGNAL_TOLERANCE = 1e-6


class RetropolationError(ValueError):
    """Raised when the urban retropolation violates its contract."""


@dataclass(frozen=True)
class RetropolationPolicy:
    """Calendar and tolerances of the urban retropolation."""

    start_period: str
    anchor_start_year: int
    end_period: str
    splice_overlap_months: int
    backtest_calibration_years: Sequence[int]
    anchor_tolerance: float


@dataclass(frozen=True)
class RetropolationResult:
    """Monthly signals and audit tables."""

    monthly: pd.DataFrame
    unreconciled: pd.DataFrame
    anchor_audit: pd.DataFrame
    splice_factors: pd.DataFrame
    seam_audit: pd.DataFrame
    backtest: pd.DataFrame


def build_annual_anchors(
    history: Mapping[int, pd.DataFrame],
    closed_panel: pd.DataFrame,
    *,
    city_names: Mapping[int, str],
    recipient_codes: Sequence[int],
    years: Sequence[int],
) -> pd.DataFrame:
    """Assemble the 2007-2020 annual anchors of the 32 cities.

    Raises
    ------
    RetropolationError
        On incomplete, duplicated or non-positive anchors.
    """
    recipients = set(recipient_codes)
    rows: list[dict[str, Any]] = []
    for code in sorted(city_names):
        if code in recipients:
            continue
        frame = history[code]
        for year in years:
            rows.append(
                {
                    "city_code": code,
                    "city_name": city_names[code],
                    "year": year,
                    "anchor_type": ANCHOR_GEIH,
                    "donor_code": code,
                    **{q: float(frame.loc[year, q]) for q in URBAN_SIGNALS},
                }
            )
    for record in closed_panel[
        closed_panel["year"] <= max(years)
    ].itertuples():
        rows.append(
            {
                "city_code": int(record.recipient_code),
                "city_name": str(record.recipient_name),
                "year": int(record.year),
                "anchor_type": ANCHOR_DONOR,
                "donor_code": int(record.donor_code),
                **{q: float(getattr(record, q)) for q in URBAN_SIGNALS},
            }
        )
    anchors = (
        pd.DataFrame(rows)
        .sort_values(["city_code", "year"])
        .reset_index(drop=True)
    )
    if set(anchors["city_code"]) != set(city_names) or len(anchors) != len(
        city_names
    ) * len(years):
        raise RetropolationError("Anchors must cover every city and year")
    if anchors.duplicated(subset=["city_code", "year"]).any():
        raise RetropolationError("Duplicated anchors")
    values = np.array(anchors[list(URBAN_SIGNALS)], dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise RetropolationError("Anchors must be positive")
    return anchors


class UrbanRetropolation:
    """Build monthly urban signals from annual anchors and the national."""

    def __init__(
        self, policy: RetropolationPolicy, recipient_codes: Sequence[int]
    ) -> None:
        """Store the calendar policy and the recipient codes."""
        self._policy = policy
        self._recipients = set(recipient_codes)
        self._months = pd.period_range(
            policy.start_period, policy.end_period, freq="M"
        )
        self._anchor_years = list(
            range(policy.anchor_start_year, self._months[-1].year + 1)
        )

    def run(
        self, anchors: pd.DataFrame, national: pd.DataFrame
    ) -> RetropolationResult:
        """Run the retropolation for every city in ``anchors``."""
        national = self._national_window(national)
        monthly, raw, anchor_audit, links, seams = [], [], [], [], []
        for code, group in anchors.groupby("city_code", sort=True):
            city = self._city(int(code), group.set_index("year"), national)
            monthly.append(city["monthly"])
            raw.append(city["raw"])
            anchor_audit.extend(city["anchor_audit"])
            links.extend(city["links"])
            seams.extend(city["seams"])
        result = RetropolationResult(
            monthly=pd.concat(monthly, ignore_index=True),
            unreconciled=pd.concat(raw, ignore_index=True),
            anchor_audit=pd.DataFrame(anchor_audit),
            splice_factors=pd.DataFrame(links),
            seam_audit=pd.DataFrame(seams),
            backtest=self.backtest(anchors, national),
        )
        self._verify(result)
        return result

    def _national_window(self, national: pd.DataFrame) -> pd.DataFrame:
        data = national.copy()
        data.index = pd.PeriodIndex(data["period"].astype(str), freq="M")
        data = data.loc[
            self._months[0] : self._months[-1], list(URBAN_SIGNALS)
        ]
        if (
            not data.index.equals(self._months)
            or data.isna().any().any()
            or (data <= 0).any().any()
        ):
            raise RetropolationError("National series must cover the window")
        return data

    def _city(
        self, code: int, anchors: pd.DataFrame, national: pd.DataFrame
    ) -> dict[str, Any]:
        policy = self._policy
        name = str(anchors.iloc[0]["city_name"])
        first_anchor = policy.anchor_start_year
        corrected: dict[int, np.ndarray] = {}
        audit_rows = []
        for year, row in anchors.iterrows():
            source = np.array(row[list(URBAN_SIGNALS)], dtype=float)
            reconciled = project_signals(source[None, :], source)[0]
            corrected[int(year)] = reconciled
            for position, quantity in enumerate(URBAN_SIGNALS):
                audit_rows.append(
                    {
                        "city_code": code,
                        "city_name": name,
                        "year": int(year),
                        "quantity": quantity,
                        "source": row["anchor_type"],
                        "source_value": source[position],
                        "reconciled_value": reconciled[position],
                        "delta": reconciled[position] - source[position],
                        "relative_delta": reconciled[position]
                        / source[position]
                        - 1,
                    }
                )

        profiles = []
        for year in self._anchor_years:
            reference = np.array(national.loc[str(year)], dtype=float)
            target = corrected[year]
            scaled = reference * target / reference.mean(axis=0)
            reconciled = project_signals(scaled, target)
            if not np.allclose(
                reconciled.mean(axis=0),
                target,
                rtol=0,
                atol=policy.anchor_tolerance,
            ):
                raise RetropolationError(f"Anchor lost: {code} {year}")
            profiles.append((scaled, reconciled))
        scaled_all = np.vstack([p[0] for p in profiles])
        anchored_months = pd.period_range(
            f"{first_anchor}-01", self._months[-1], freq="M"
        )
        provisional = pd.DataFrame(
            scaled_all, index=anchored_months, columns=list(URBAN_SIGNALS)
        )

        raw = pd.DataFrame(
            index=self._months, columns=list(URBAN_SIGNALS), dtype=float
        )
        links = []
        link_end = f"{first_anchor}-12"
        for position, quantity in enumerate(URBAN_SIGNALS):
            splice = SeriesSplicer(
                method="ratio",
                overlap_periods=policy.splice_overlap_months,
            ).splice(national.loc[:link_end, quantity], provisional[quantity])
            raw[quantity] = splice.values.reindex(  # noqa: PD011
                self._months
            ).astype(float)
            if raw[quantity].isna().any():
                raise RetropolationError(f"Incomplete splice {code}")
            ratio = float(splice.link["ratio"])
            national_mean = float(
                national.loc[str(first_anchor), quantity].mean()
            )
            expected = corrected[first_anchor][position] / national_mean
            if abs(expected - ratio) > max(
                _SPLICE_ABSOLUTE_TOLERANCE,
                abs(expected) * _SPLICE_RELATIVE_TOLERANCE,
            ):
                raise RetropolationError("Splice ratio differs from anchor")
            links.append(
                {
                    "city_code": code,
                    "city_name": name,
                    "quantity": quantity,
                    "indicator": f"national_{quantity}",
                    "link_year": first_anchor,
                    "link_factor": ratio,
                    "city_anchor": corrected[first_anchor][position],
                    "national_mean": national_mean,
                }
            )
        if not np.allclose(
            np.array(raw.loc[anchored_months]),
            scaled_all,
            atol=_LINK_TOLERANCE,
            rtol=0,
        ):
            raise RetropolationError("Splice changed the anchored period")

        before = self._months[self._months.year < first_anchor]
        early = project_signals(
            np.array(raw.loc[before], dtype=float), corrected[first_anchor]
        )
        final = np.vstack([early, np.vstack([p[1] for p in profiles])])
        if not (np.isfinite(final).all() and (final > 0).all()):
            raise RetropolationError(f"Invalid signals for {name}")
        history = pd.DataFrame(
            final, index=self._months, columns=list(URBAN_SIGNALS)
        )
        for year in self._anchor_years:
            if not np.allclose(
                np.array(history.loc[str(year)].mean()),
                corrected[year],
                rtol=0,
                atol=policy.anchor_tolerance,
            ):
                raise RetropolationError(f"Anchor not kept {code} {year}")

        origin = np.where(
            self._months.year < first_anchor,
            ORIGIN_RETROPOLATED,
            ORIGIN_DONOR_ANCHOR
            if code in self._recipients
            else ORIGIN_GEIH_ANCHOR,
        )
        frames = {}
        for key, values in (("monthly", history), ("raw", raw)):
            frame = values.reset_index(drop=True)
            frame.insert(0, "origin", origin)
            frame.insert(0, "period", self._months.astype(str))
            frame.insert(0, "city_name", name)
            frame.insert(0, "city_code", code)
            frames[key] = frame

        last = pd.Period(f"{first_anchor - 1}-12", freq="M")
        first = pd.Period(f"{first_anchor}-01", freq="M")
        city_gap = np.log(
            np.array(history.loc[first]) / np.array(history.loc[last])
        )
        national_gap = np.log(
            np.array(national.loc[first]) / np.array(national.loc[last])
        )
        seams = []
        for position, quantity in enumerate(URBAN_SIGNALS):
            closure = (
                history.loc[before, quantity] - raw.loc[before, quantity]
            ) / raw.loc[before, quantity]
            ratio = raw.loc[before, quantity] / national.loc[before, quantity]
            seams.append(
                {
                    "city_code": code,
                    "city_name": name,
                    "quantity": quantity,
                    "seam_log": float(city_gap[position]),
                    "national_seam_log": float(national_gap[position]),
                    "seam_extra_log": float(
                        city_gap[position] - national_gap[position]
                    ),
                    "max_relative_closure_before_anchor": float(
                        np.max(np.abs(closure))
                    ),
                    "max_signal_ratio_error_before_anchor": float(
                        np.max(
                            np.abs(
                                ratio
                                - corrected[first_anchor][position]
                                / national.loc[
                                    str(first_anchor), quantity
                                ].mean()
                            )
                        )
                    ),
                }
            )
        return {
            "monthly": frames["monthly"],
            "raw": frames["raw"],
            "anchor_audit": audit_rows,
            "links": links,
            "seams": seams,
        }

    def backtest(
        self, anchors: pd.DataFrame, national: pd.DataFrame
    ) -> pd.DataFrame:
        """Hide years before a calibration year and rescale the national.

        Only cities with genuine GEIH history are evaluated.
        """
        national_annual = national.groupby(national.index.year).mean()
        rows = []
        for code, group in anchors.groupby("city_code"):
            if int(code) in self._recipients:
                continue
            frame = group.set_index("year")
            for calibration in self._policy.backtest_calibration_years:
                hidden = list(
                    range(self._policy.anchor_start_year, calibration)
                )
                for quantity in URBAN_SIGNALS:
                    reference = national_annual[quantity]
                    predicted = (
                        np.array(reference.loc[hidden], dtype=float)
                        * float(frame.loc[calibration, quantity])
                        / float(reference.loc[calibration])
                    )
                    actual = np.array(frame.loc[hidden, quantity], dtype=float)
                    rows.append(
                        {
                            "city_code": int(code),
                            "city_name": str(frame.iloc[0]["city_name"]),
                            "calibration_year": calibration,
                            "hidden_start": hidden[0],
                            "hidden_end": hidden[-1],
                            "quantity": quantity,
                            "wape_pct": float(
                                np.abs(actual - predicted).sum()
                                / actual.sum()
                                * 100
                            ),
                            "max_ape_pct": float(
                                np.max(
                                    np.abs(actual - predicted) / actual * 100
                                )
                            ),
                        }
                    )
        return pd.DataFrame(rows)

    def _verify(self, result: RetropolationResult) -> None:
        monthly = result.monthly
        if not np.allclose(
            monthly["labor_force"],
            monthly["employed"] + monthly["unemployed"],
            atol=_IDENTITY_TOLERANCE,
            rtol=0,
        ):
            raise RetropolationError("Labor force identity broken")
        if not np.allclose(
            monthly["working_age"],
            monthly["labor_force"] + monthly["inactive"],
            atol=_IDENTITY_TOLERANCE,
            rtol=0,
        ):
            raise RetropolationError("Working-age identity broken")
        if (
            monthly["working_age"]
            > monthly["population"] + _IDENTITY_TOLERANCE
        ).any():
            raise RetropolationError("Working age above population")
        ratio_error = result.seam_audit[
            "max_signal_ratio_error_before_anchor"
        ].max()
        if ratio_error >= _RATIO_SIGNAL_TOLERANCE:
            raise RetropolationError("Pre-anchor signal is not proportional")
