"""Department = represented capital + estimated rest of the territory.

For the nine Amazonía/Orinoquía/San Andrés territories, GEIH represents
only the capital's municipal head. Their departmental totals are built as
the capital's urban signal plus an estimated rest, whose population is the
departmental demographic projection minus the capital's population and
whose labor ratios come from a chosen method.

The method is validated on the 22 anchored non-synthetic departments,
where the rest is observable (anchor minus capital): each department is
rebuilt as capital + estimated rest without its own anchors, and compared
with them.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

LEVELS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
)
RATIOS: tuple[str, ...] = (
    "working_age_ratio",
    "participation",
    "unemployment",
)
METHODS: tuple[str, ...] = (
    "capital",
    "national",
    "pooled",
    "nearest",
    "nearest3",
)


class ComplementError(ValueError):
    """Raised when a rest of territory cannot be built."""


def ratios(frame: pd.DataFrame) -> pd.DataFrame:
    """Working age/population, participation and unemployment ratios."""
    return pd.DataFrame(
        {
            "working_age_ratio": frame["working_age"] / frame["population"],
            "participation": frame["labor_force"] / frame["working_age"],
            "unemployment": frame["unemployed"] / frame["labor_force"],
        },
        index=frame.index,
    )


def observed_rest(
    departments: pd.DataFrame, cities: pd.DataFrame
) -> pd.DataFrame:
    """Department minus capital, per department and year (annual means).

    Monthly differences are not used: both monthly paths are
    reconstructions (latent city months, disaggregated departmental
    months) and their difference can be negative in single months. Annual
    means are where both series rest on official figures.

    Raises
    ------
    ComplementError
        If an annual rest level is not positive.
    """
    keys = ["dep_code", "period"]
    merged = departments.set_index(keys)[list(LEVELS)].join(
        cities.rename(columns={"city_code": "dep_code"}).set_index(keys)[
            list(LEVELS)
        ],
        rsuffix="_city",
        how="inner",
    )
    rest = pd.DataFrame(
        {level: merged[level] - merged[f"{level}_city"] for level in LEVELS},
        index=merged.index,
    )
    years = rest.index.get_level_values("period").str.slice(0, 4)
    annual = rest.groupby(
        [rest.index.get_level_values("dep_code"), years]
    ).mean()
    annual.index = annual.index.set_names(["dep_code", "year"])
    if (
        (annual[["employed", "unemployed", "inactive", "population"]] <= 0)
        .any()
        .any()
    ):
        raise ComplementError("Non-positive observed rest of territory")
    return annual


def build_department(
    city: pd.DataFrame, population: pd.Series, rest_ratios: pd.DataFrame
) -> pd.DataFrame:
    """Capital levels plus a rest built from population and ratios.

    ``city`` and ``rest_ratios`` are indexed by period; ``population`` is
    the departmental total population by period.

    Raises
    ------
    ComplementError
        If the capital population exceeds the departmental population.
    """
    rest_population = population - city["population"]
    if (rest_population <= 0).any():
        raise ComplementError("Capital population exceeds the department")
    working_age = rest_population * rest_ratios["working_age_ratio"]
    labor_force = working_age * rest_ratios["participation"]
    unemployed = labor_force * rest_ratios["unemployment"]
    rest = pd.DataFrame(
        {
            "population": rest_population,
            "working_age": working_age,
            "labor_force": labor_force,
            "unemployed": unemployed,
            "employed": labor_force - unemployed,
            "inactive": working_age - labor_force,
        }
    )
    return city[list(LEVELS)] + rest[list(LEVELS)]


class RestRatioEstimator:
    """Rest-of-territory ratios for a target from donors' observed rest."""

    def __init__(
        self,
        observed: pd.DataFrame,
        national: pd.DataFrame,
        cities: pd.DataFrame,
        profiles: pd.DataFrame,
    ) -> None:
        """Store observed rests, national series, city signals, profiles."""
        self._observed = observed
        self._national = ratios(national.set_index("period")[list(LEVELS)])
        self._cities = cities.set_index(["city_code", "period"])
        standardized = (profiles - profiles.mean()) / profiles.std(ddof=0)
        self._profiles = standardized

    def neighbors(
        self, target: int, donors: Sequence[int], k: int
    ) -> list[int]:
        """Return the ``k`` donors closest to ``target`` in profile space."""
        candidates = [d for d in donors if d != target]
        distance = (
            (self._profiles.loc[candidates] - self._profiles.loc[target]) ** 2
        ).sum(axis=1)
        return list(distance.sort_values().index[:k].astype(int))

    def estimate(
        self,
        method: str,
        target: int,
        donors: Sequence[int],
        periods: Sequence[str],
    ) -> pd.DataFrame:
        """Return rest ratios by period for ``target``.

        Raises
        ------
        ComplementError
            On an unknown method.
        """
        pool = [d for d in donors if d != target]
        if method == "capital":
            frame = self._cities.loc[target].loc[list(periods), list(LEVELS)]
            return ratios(frame)
        if method == "national":
            return self._national.loc[list(periods)]
        if method == "pooled":
            chosen = pool
        elif method == "nearest":
            chosen = self.neighbors(target, pool, 1)
        elif method == "nearest3":
            chosen = self.neighbors(target, pool, 3)
        else:
            raise ComplementError(f"Unknown method: {method}")
        rest = self._observed.loc[
            self._observed.index.get_level_values("dep_code").isin(chosen)
        ]
        if method == "nearest3":
            yearly = ratios(rest).groupby(level="year").mean()
        else:
            yearly = ratios(rest.groupby(level="year")[list(LEVELS)].sum())
        years = [p[:4] for p in periods]
        result = yearly.reindex(years)
        result.index = list(periods)
        return result
