"""Validated access to the urban source tables.

* Historical signals: one row per code and year, with GEIH annual values
  (``<token>_geih``, thousands of persons) for the 23 cities with history,
  plus departmental anchors for the synthetic signal.
* Window proxies: annual aggregates of published 12-month rolling windows
  (persons) for the 32 cities, 2021 onward. They are not calendar years.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from icml.national.schema import source_token
from icml.urban.accounting import URBAN_SIGNALS

CODE_COLUMN = "dep_code"
YEAR_COLUMN = "year"


class UrbanInputError(ValueError):
    """Raised when an urban source does not satisfy its contract."""


def geih_column(quantity: str) -> str:
    """Return the historical GEIH column of a canonical quantity."""
    return f"{source_token(quantity)}_geih"


def anchor_column(quantity: str) -> str:
    """Return the plain (departmental-anchor / proxy) column of a quantity."""
    return source_token(quantity)


def _canonical(
    frame: pd.DataFrame, columns: Mapping[str, str]
) -> pd.DataFrame:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise UrbanInputError(f"Missing columns: {missing}")
    return frame.rename(columns=dict(columns))


@dataclass(frozen=True)
class UrbanSources:
    """Validated urban inputs.

    Attributes
    ----------
    history : Mapping[int, pandas.DataFrame]
        GEIH annual history in persons, by city code, indexed by year
        (only codes with complete GEIH values).
    proxies : Mapping[int, pandas.DataFrame]
        Window proxies in persons, by city code, indexed by year.
    raw_history : pandas.DataFrame
        Original historical table (kept for the synthetic signal).
    """

    history: Mapping[int, pd.DataFrame]
    proxies: Mapping[int, pd.DataFrame]
    raw_history: pd.DataFrame


def load_urban_sources(
    historical: pd.DataFrame,
    proxies: pd.DataFrame,
    *,
    city_codes: Sequence[int],
    excluded_codes: Sequence[int],
    selection_years: Sequence[int],
    published_unit_persons: float,
) -> UrbanSources:
    """Validate the urban sources and index them by city.

    Raises
    ------
    UrbanInputError
        On coverage gaps, duplicated keys or non-positive proxies.
    """
    expected = set(city_codes)
    if set(proxies[CODE_COLUMN]) != expected:
        raise UrbanInputError("Proxies must cover exactly the 32 cities")
    if set(historical[CODE_COLUMN]) != expected | set(excluded_codes):
        raise UrbanInputError("Historical signals have unexpected codes")
    for frame, name in ((proxies, "proxies"), (historical, "history")):
        if frame.duplicated(subset=[CODE_COLUMN, YEAR_COLUMN]).any():
            raise UrbanInputError(f"Duplicated code-year rows in {name}")

    proxy_columns = {anchor_column(q): q for q in URBAN_SIGNALS}
    proxy_table = _canonical(proxies, proxy_columns)
    proxy_by_city: dict[int, pd.DataFrame] = {}
    for code, group in proxy_table.groupby(CODE_COLUMN):
        indexed = group.set_index(YEAR_COLUMN).sort_index()
        if not set(selection_years) <= set(indexed.index):
            raise UrbanInputError(f"Proxies miss selection years: {code}")
        values = np.array(indexed[list(URBAN_SIGNALS)], dtype=float)
        if not np.isfinite(values).all() or (values <= 0).any():
            raise UrbanInputError(f"Non-positive proxies for {code}")
        proxy_by_city[int(code)] = indexed

    geih_columns = {geih_column(q): q for q in URBAN_SIGNALS}
    missing = sorted(set(geih_columns) - set(historical.columns))
    if missing:
        raise UrbanInputError(f"Missing historical columns: {missing}")
    history_table = historical[[CODE_COLUMN, YEAR_COLUMN, *geih_columns]]
    history_table = history_table.rename(columns=geih_columns)
    history_by_city: dict[int, pd.DataFrame] = {}
    for code, group in history_table.groupby(CODE_COLUMN):
        if group["employed"].isna().any():
            continue
        indexed = group.set_index(YEAR_COLUMN).sort_index()
        indexed[list(URBAN_SIGNALS)] = (
            indexed[list(URBAN_SIGNALS)] * published_unit_persons
        )
        history_by_city[int(code)] = indexed
    return UrbanSources(
        history=history_by_city, proxies=proxy_by_city, raw_history=historical
    )
