"""Departmental product with representativeness factors.

Every territory publishes its whole-territory levels. A factor per
territory, month and quantity says which share of those levels the GEIH
national total represents, so that

    sum over territories of factor x level = DANE national total

holds exactly. The ICML national total (sum of levels) is therefore
larger than DANE's by the population GEIH does not represent.

* 23 anchored departments: anchored monthly reconstruction, factor 1.
* Bogotá: its GEIH urban domain (fully represented), factor 1.
* Nine partially represented territories (Amazonía, Orinoquía, San
  Andrés): capital urban signal + rest of territory. The rest population
  is the departmental demographic projection minus the capital; its labor
  ratios are the unweighted mean of the anchored departments' observed
  rest (department minus capital, annual means). Their capitals enter the
  national total only from the month DANE incorporated them (2014-01);
  before 2014, their GEIH coverage factor is 0, except that for
  1993-2000 all factors are set to 1 because that period has no
  observed GEIH national coverage and is reconstructed in full.
* DANE's own domains do not add up exactly: with fully official figures
  (national monthly, departmental annex, published 12-month windows),
  the 23 anchors plus Bogotá plus the nine capitals miss the national
  total by 0.3-1.9 % in unemployed, 0.1-0.4 % in employed and 0.014 % in
  population. Someone has to absorb that gap, and
  ``residual_allocation`` says who:

  - ``proportional`` (default, the rule the project used in its earlier
    consolidation): every represented part takes a share of the residual
    in proportion to its annual size. No official figure moves more than
    1.9 % (reached only in unemployed in 2021, the year the sampling
    frame changed); anchors are no longer exact, and the deviation each
    one takes is published in its own column.
  - ``non_anchored``: the joint smoother of the hierarchical closure
    keeps every annual anchor exact, so the whole gap falls on Bogotá and
    the capitals — up to 9.1 % of Bogotá's unemployed and 12.1 % of a
    capital's, against figures DANE publishes. Kept as an alternative.
* Months before ``reconcile_from`` are not reconciled to the national
  series. From 2001 on, the DANE national population matches the
  projections of the territories it represents within 0.1 %; before, it
  falls up to 1.6 % below them (0.55 million people in 1993), and that
  period has no official DANE national publication anyway: it is the
  project's own reconstruction. Every territory is therefore built from
  its own demographic projection and its reconstructed rates, and the
  ICML national is their sum. Population is set to the projection
  (``population_from_projection_before``) and the labor components are
  rescaled by the same factor, so every rate is preserved exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.evaluation.complement import (
    LEVELS,
    build_department,
    observed_rest,
    ratios,
)
from icml.reconciliation.solvers import joint_smoother

COMPONENTS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "population",
)
SOURCE_ANCHORED = "DEPARTAMENTO_ANCLA_ANUAL"
SOURCE_URBAN = "GEIH_DOMINIO_URBANO"
SOURCE_CAPITAL_REST = "CAPITAL_GEIH_MAS_RESTO_ESTIMADO"
_IDENTITY_TOLERANCE = 1e-6
_NATIONAL_TOLERANCE = 1e-6


class RepresentativenessError(ValueError):
    """Raised when the factor product breaks its contract."""


@dataclass(frozen=True)
class RepresentativenessPolicy:
    """Territories, dates and smoothing of the representativeness design."""

    fully_urban_codes: Sequence[int]
    partial_codes: Sequence[int]
    capitals_in_national_from: str
    excluded_donor_codes: Sequence[int]
    population_strength: float
    employed_strength: float
    unemployed_strength: float
    inactive_strength: float
    joint_tolerance_persons: float
    reconcile_from: str
    population_from_projection_before: str
    residual_allocation: str = "proportional"


REFERENCE_ANCHOR = "ancla_anual_departamental"
REFERENCE_URBAN = "geih_dominio_urbano"
REFERENCE_CAPITAL = "geih_capital_ventanas"


@dataclass(frozen=True)
class RepresentativenessResult:
    """Departmental product, ICML national total and diagnostics."""

    departmental: pd.DataFrame
    national: pd.DataFrame
    rest_ratios: pd.DataFrame
    deviation: pd.DataFrame
    summary: dict[str, Any]


class RepresentativenessBuilder:
    """Build whole-territory levels and representativeness factors."""

    def __init__(self, policy: RepresentativenessPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def rest_ratios(
        self,
        departments: pd.DataFrame,
        cities: pd.DataFrame,
        periods: Sequence[str],
    ) -> pd.DataFrame:
        """Mean observed rest ratios of the donors, by period.

        Years without donor data carry the last available year forward.
        """
        policy = self._policy
        anchored = sorted(set(departments["dep_code"].astype(int)))
        donors = [
            c for c in anchored if c not in set(policy.excluded_donor_codes)
        ]
        observed = observed_rest(
            departments[departments["dep_code"].isin(donors)],
            cities[cities["city_code"].isin(donors)],
        )
        yearly = ratios(observed).groupby(level="year").mean()
        years = [p[:4] for p in periods]
        result = (
            yearly.reindex(sorted(set(years) | set(yearly.index)))
            .ffill()
            .reindex(years)
        )
        result.index = list(periods)
        return result

    def build(
        self,
        panel: pd.DataFrame,
        departments: pd.DataFrame,
        cities: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> RepresentativenessResult:
        """Return the factor product.

        ``panel`` supplies the anchored departments' months (including
        provisional ones) and the demographic projections.

        Raises
        ------
        RepresentativenessError
            If identities, factors or the national total are violated.
        """
        policy = self._policy
        periods = sorted(panel["period"].unique())
        rest = self.rest_ratios(departments, cities, periods)
        city = cities.set_index(["city_code", "period"])
        demographic = panel.set_index(["dep_code", "period"])[
            "population_demographic_projection"
        ]
        partial = sorted(policy.partial_codes)
        urban = sorted(policy.fully_urban_codes)
        anchored = sorted(set(anchors["dep_code"].astype(int)))
        population = departments.set_index(["dep_code", "period"])[
            "population"
        ]
        represented: dict[int, pd.DataFrame] = {}
        for code in anchored:
            frame = (
                panel[panel["dep_code"] == code]
                .set_index("period")
                .loc[periods, ["employed", "unemployed", "inactive"]]
                .copy()
            )
            frame["population"] = np.array(
                population.reindex(
                    pd.MultiIndex.from_product([[code], periods])
                ).ffill(),
                dtype=float,
            )
            represented[code] = frame
        for code in (*urban, *partial):
            represented[code] = (
                city.loc[code].loc[periods, list(COMPONENTS)].copy()
            )
        if self._policy.residual_allocation == "proportional":
            adjusted, diagnostics = self._allocate_proportionally(
                represented, national, periods
            )
        else:
            adjusted, diagnostics = self._reconcile(
                represented, national, anchors, periods, partial
            )
        adjusted, early = self._project_early(
            adjusted, demographic, periods, partial
        )
        diagnostics.update(early)
        scope = [p for p in periods if p >= policy.reconcile_from]
        frames = [
            self._with_residual(
                self._territory(
                    code, frame, partial, urban, demographic, rest, periods
                ),
                represented[code],
                scope,
            )
            for code, frame in adjusted.items()
        ]
        result = self._factors(pd.concat(frames, ignore_index=True))
        in_scope = result["period"] >= policy.reconcile_from
        self._verify(
            result[in_scope],
            national[national["period"] >= policy.reconcile_from],
        )
        icml_national = self._national(result, national)
        scoped = icml_national["period"] >= policy.reconcile_from
        summary = {
            "reconciled_from": policy.reconcile_from,
            "max_factor_full_territories_deviation": float(
                np.abs(
                    result.loc[
                        in_scope & (result["source"] != SOURCE_CAPITAL_REST),
                        [f"factor_{q}" for q in COMPONENTS],
                    ]
                    - 1
                )
                .max()
                .max()
            ),
            **diagnostics,
            "icml_minus_dane_population_pct": {
                "min": float(
                    icml_national.loc[
                        scoped, "coverage_gap_population_pct"
                    ].min()
                ),
                "max": float(
                    icml_national.loc[
                        scoped, "coverage_gap_population_pct"
                    ].max()
                ),
            },
        }
        deviation = self._deviation(result, anchors, periods)
        summary["official_deviation_pct"] = {
            quantity: round(float(group["deviation_pct"].abs().max()), 3)
            for quantity, group in deviation.groupby("quantity")
        }
        return RepresentativenessResult(
            departmental=result,
            national=icml_national,
            deviation=deviation,
            rest_ratios=rest.reset_index().rename(columns={"index": "period"}),
            summary=summary,
        )

    @staticmethod
    def _with_residual(
        levels: pd.DataFrame, baseline: pd.DataFrame, months: Sequence[str]
    ) -> pd.DataFrame:
        """Record how much of the national residual this part absorbed.

        The difference between the represented part as published and the
        official figure it started from, so a user can see how much of
        the sources' non-additivity each territory carries.
        """
        result = levels.set_index("period")
        for quantity in COMPONENTS:
            share = pd.Series(0.0, index=result.index)
            before = np.array(baseline.loc[months, quantity], dtype=float)
            after = np.array(
                result.loc[months, f"{quantity}_represented"], dtype=float
            )
            # A capital outside the national total in that month carries
            # no residual: its represented part is zero by design.
            share.loc[months] = np.where(after > 0, after - before, 0.0)
            result[f"{quantity}_residual_share"] = share
        return result.reset_index()

    def _territory(
        self,
        code: int,
        frame: pd.DataFrame,
        partial: Sequence[int],
        urban: Sequence[int],
        demographic: pd.Series,
        rest: pd.DataFrame,
        periods: list[str],
    ) -> pd.DataFrame:
        """Whole-territory levels and represented components."""
        if code in set(partial):
            capital = frame.copy()
            capital["labor_force"] = (
                capital["employed"] + capital["unemployed"]
            )
            capital["working_age"] = (
                capital["labor_force"] + capital["inactive"]
            )
            full = build_department(
                capital, demographic.loc[code].loc[periods], rest
            )
            source = SOURCE_CAPITAL_REST
            # share = capital signal for all periods (not zeroed before 2014).
            # factor = capital / full, which varies smoothly with demographics,
            # so there is no artificial jump when DANE started publishing these
            # territories. The ICML total (full) is always the whole department.
            share = frame.copy()
        else:
            full = frame.copy()
            full["labor_force"] = full["employed"] + full["unemployed"]
            full["working_age"] = full["labor_force"] + full["inactive"]
            source = SOURCE_URBAN if code in set(urban) else SOURCE_ANCHORED
            share = frame.copy()
        levels = full[list(LEVELS)].copy()
        for quantity in COMPONENTS:
            levels[f"{quantity}_represented"] = share[quantity]
        levels = levels.reset_index().rename(columns={"index": "period"})
        levels.insert(0, "dep_code", code)
        levels["source"] = source
        return levels

    def _project_early(
        self,
        adjusted: dict[int, pd.DataFrame],
        demographic: pd.Series,
        periods: list[str],
        partial: Sequence[int],
    ) -> tuple[dict[int, pd.DataFrame], dict[str, Any]]:
        """Put early months on the demographic projection, rates intact.

        Applies to territories published as whole territories (the
        anchored departments and Bogotá). The nine partially represented
        territories take their projection through the rest of territory,
        so only their capital is left untouched here.
        """
        policy = self._policy
        early = [
            p for p in periods if p < policy.population_from_projection_before
        ]
        changes: dict[str, Any] = {}
        if not early:
            return adjusted, changes
        largest = 0.0
        for code, frame in adjusted.items():
            if code in set(partial):
                continue
            target = np.array(demographic.loc[code].loc[early], dtype=float)
            ratio = target / np.array(
                frame.loc[early, "population"], dtype=float
            )
            largest = max(largest, float(np.max(np.abs(ratio - 1))))
            for quantity in COMPONENTS:
                frame.loc[early, quantity] = (
                    np.array(frame.loc[early, quantity], dtype=float) * ratio
                )
        changes["max_early_population_rescaling_pct"] = 100 * largest
        changes["population_from_projection_before"] = (
            policy.population_from_projection_before
        )
        return adjusted, changes

    def _allocate_proportionally(
        self,
        represented: dict[int, pd.DataFrame],
        national: pd.DataFrame,
        periods: list[str],
    ) -> tuple[dict[int, pd.DataFrame], dict[str, Any]]:
        """Spread the national residual over every represented part.

        ``value = base + share x residual`` with ``share`` the unit's
        annual mean over the total, the rule used in the project's
        earlier consolidation. Annual anchors are no longer exact: the
        deviation each one takes is reported.
        """
        policy = self._policy
        reference = national.set_index("period")
        months = [p for p in periods if p >= policy.reconcile_from]
        adjusted = {code: frame.copy() for code, frame in represented.items()}
        entry = policy.capitals_in_national_from
        codes = sorted(represented)
        partial = set(policy.partial_codes)
        # A capital shares the residual only once DANE incorporated it.
        inside = pd.DataFrame(
            {
                code: (np.array(months) >= entry)
                if code in partial
                else np.ones(len(months), dtype=bool)
                for code in codes
            },
            index=months,
        )
        deviation = 0.0
        for quantity in COMPONENTS:
            base = pd.DataFrame(
                {
                    code: represented[code].loc[months, quantity]
                    for code in codes
                }
            ).where(inside, 0.0)
            years = base.index.str.slice(0, 4)
            weight = base.groupby(years).transform("mean")
            share = weight.div(weight.sum(axis=1), axis=0)
            residual = np.array(
                reference.loc[months, quantity], dtype=float
            ) - np.array(base.sum(axis=1))
            allocated = base.add(share.mul(residual, axis=0))
            ratio = (allocated / base.where(base > 0) - 1).abs()
            deviation = max(deviation, float(ratio.max().max()))
            for code in codes:
                adjusted[code].loc[months, quantity] = np.where(
                    inside[code],
                    allocated[code],
                    represented[code].loc[months, quantity],
                )
        return adjusted, {
            "residual_allocation": "proportional",
            "max_monthly_deviation_pct": 100 * deviation,
        }

    def _reconcile(
        self,
        represented: dict[int, pd.DataFrame],
        national: pd.DataFrame,
        anchors: pd.DataFrame,
        periods: list[str],
        partial: Sequence[int],
    ) -> tuple[dict[int, pd.DataFrame], dict[str, Any]]:
        """Joint smoothing of represented parts onto national months.

        Runs separately before and after the capitals' entry, because the
        set of represented units changes then.
        """
        policy = self._policy
        strengths = {
            "population": policy.population_strength,
            "employed": policy.employed_strength,
            "unemployed": policy.unemployed_strength,
            "inactive": policy.inactive_strength,
        }
        reference = national.set_index("period")
        adjusted = {code: frame.copy() for code, frame in represented.items()}
        # All territories have a real signal from reconcile_from onward.
        for start, end in ((policy.reconcile_from, "9999-12"),):
            months = [p for p in periods if start <= p < end]
            if not months:
                continue
            codes = list(represented)

            years = np.array([int(p[:4]) for p in months])
            segment = anchors[anchors["year"].isin(set(years.tolist()))]
            for quantity, strength in strengths.items():
                baseline = np.column_stack(
                    [
                        np.array(
                            represented[c].loc[months, quantity], dtype=float
                        )
                        for c in codes
                    ]
                )
                smoothed = joint_smoother(
                    baseline,
                    codes,
                    years,
                    np.array(reference.loc[months, quantity], dtype=float),
                    segment,
                    strength,
                    list(segment[quantity]),
                    policy.joint_tolerance_persons,
                )
                for position, code in enumerate(codes):
                    adjusted[code].loc[months, quantity] = smoothed[
                        :, position
                    ]
        diagnostics: dict[str, Any] = {}
        window = [p for p in periods if p >= policy.reconcile_from]
        for code in policy.fully_urban_codes:
            for quantity in COMPONENTS:
                change = (
                    adjusted[code].loc[window, quantity]
                    / represented[code].loc[window, quantity]
                    - 1
                )
                yearly = change.groupby(change.index.str.slice(0, 4)).mean()
                diagnostics[
                    f"urban_{code}_max_annual_change_pct_{quantity}"
                ] = float(100 * yearly.abs().max())
        return adjusted, diagnostics

    @staticmethod
    def _factors(merged: pd.DataFrame) -> pd.DataFrame:
        merged = merged.copy()
        # Pre-GEIH years have no observed national coverage to exclude.
        # Identity policy preserves ALL reconstructed territorial levels.
        early = merged["period"].astype(str).lt("2001-01")
        for quantity in COMPONENTS:
            merged.loc[early, f"{quantity}_represented"] = merged.loc[early, quantity]
        merged["factor_reference_status"] = np.where(
            early, "SIN_REFERENCIA_GEIH_FACTOR_IDENTIDAD", "COBERTURA_GEIH"
        )
        merged["labor_force_represented"] = (
            merged["employed_represented"] + merged["unemployed_represented"]
        )
        merged["working_age_represented"] = (
            merged["labor_force_represented"] + merged["inactive_represented"]
        )
        for quantity in LEVELS:
            merged[f"factor_{quantity}"] = (
                merged[f"{quantity}_represented"] / merged[quantity]
            )
        merged["year"] = merged["period"].str.slice(0, 4).astype(int)
        merged["unemployment_rate"] = (
            merged["unemployed"] / merged["labor_force"]
        )
        merged["employment_rate"] = merged["employed"] / merged["working_age"]
        merged["participation_rate"] = (
            merged["labor_force"] / merged["working_age"]
        )
        return merged

    def _deviation(
        self, result: pd.DataFrame, anchors: pd.DataFrame, periods: list[str]
    ) -> pd.DataFrame:
        """Deviation of every published figure from its official source.

        One row per territory, year and quantity. The reference is the
        annual departmental anchor for the 23, and the GEIH figure the
        represented part started from for Bogotá and the capitals. This
        is the honest headline accuracy of the whole method, not of the
        predictive model alone; ``absorbed_residual_persons`` says how
        much of it comes from the sources not adding up.
        """
        policy = self._policy
        scope = result[result["period"] >= policy.reconcile_from]
        official = anchors.set_index(["dep_code", "year"])
        rows = []
        for quantity in COMPONENTS:
            annual = scope.groupby(["dep_code", "year"]).agg(
                published=(quantity, "mean"),
                represented=(f"{quantity}_represented", "mean"),
                absorbed=(f"{quantity}_residual_share", "mean"),
                source=("source", "first"),
            )
            for (code, year), row in annual.iterrows():
                if row["source"] == SOURCE_ANCHORED:
                    if (code, year) not in official.index:
                        continue
                    reference = float(official.loc[(code, year), quantity])
                    kind = REFERENCE_ANCHOR
                    published = float(row["published"])
                else:
                    reference = float(row["represented"] - row["absorbed"])
                    kind = (
                        REFERENCE_URBAN
                        if row["source"] == SOURCE_URBAN
                        else REFERENCE_CAPITAL
                    )
                    published = float(row["represented"])
                if reference <= 0:
                    continue
                rows.append(
                    {
                        "dep_code": int(code),
                        "year": int(year),
                        "quantity": quantity,
                        "reference_type": kind,
                        "published": published,
                        "official": reference,
                        "deviation_persons": published - reference,
                        "deviation_pct": 100 * (published / reference - 1),
                        "absorbed_residual_persons": float(row["absorbed"]),
                    }
                )
        return pd.DataFrame(rows)

    @staticmethod
    def _national(
        result: pd.DataFrame, national: pd.DataFrame
    ) -> pd.DataFrame:
        totals = result.groupby("period")[list(LEVELS)].sum()
        dane = national.set_index("period").loc[totals.index]
        frame = totals.add_prefix("icml_").join(
            dane[list(LEVELS)].add_prefix("dane_")
        )
        for quantity in LEVELS:
            frame[f"coverage_gap_{quantity}"] = (
                frame[f"icml_{quantity}"] - frame[f"dane_{quantity}"]
            )
        frame["coverage_gap_population_pct"] = 100 * (
            frame["icml_population"] / frame["dane_population"] - 1
        )
        return frame.reset_index()

    @staticmethod
    def _verify(result: pd.DataFrame, national: pd.DataFrame) -> None:
        if (
            max(
                float(
                    (
                        result["labor_force"]
                        - result["employed"]
                        - result["unemployed"]
                    )
                    .abs()
                    .max()
                ),
                float(
                    (
                        result["working_age"]
                        - result["labor_force"]
                        - result["inactive"]
                    )
                    .abs()
                    .max()
                ),
            )
            > _IDENTITY_TOLERANCE
        ):
            raise RepresentativenessError("Identities not closed")
        if (result[list(LEVELS)] <= 0).any().any() or (
            result["working_age"] > result["population"]
        ).any():
            raise RepresentativenessError("Inadmissible levels")
        if (result[[f"factor_{q}" for q in COMPONENTS]] < 0).any().any():
            raise RepresentativenessError("Negative factor")
        # The ICML national total is the sum of all 33 territories (larger
        # than DANE's because it covers all departments, including the nine
        # that DANE does not fully represent). We no longer require that the
        # weighted sum equals the DANE national figure; instead we only
        # check that factors are in [0, 1] and that the weighted sum does
        # not exceed the full territory sum (which would indicate a bug).
        for quantity in COMPONENTS:
            full_sum = result.groupby("period")[quantity].sum()
            weighted = (
                result.assign(
                    v=result[quantity] * result[f"factor_{quantity}"]
                )
                .groupby("period")["v"]
                .sum()
            )
            if (np.array(weighted) > np.array(full_sum) + _NATIONAL_TOLERANCE).any():
                raise RepresentativenessError(
                    f"Weighted sum exceeds full territory sum: {quantity}"
                )
