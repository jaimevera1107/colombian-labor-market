"""Splice of the unobserved informality segment to the first observed regime.

Until 2000-12 the informality rate comes from a retropolation with no official
anchor; from 2001-01 it is anchored to DANE. The two regimes do not meet: the
rate steps up by about 2.8 points in one month in the national series, in all
33 cities and in 29 of 33 departments. That step is a level break between two
measurement regimes, not a change in the world.

The anchored side has information and the retropolated side has none, so the
retropolated side moves: its level is shifted by a constant estimated at the
break, keeping its monthly dynamics, and everything from the break month on is
left untouched.

* The break is estimated with a regression discontinuity over a window of
  months on each side, with a slope common to both sides. A difference of
  yearly means mixes the break with a year of drift, and a one-month difference
  amplifies the noise of a single month.
* Each series gets its own break: the national target, every department (so
  the departments stay continuous, and still add up to the national target
  through the existing calibration) and every city.

The splice is a methodological change, not part of the equivalence refactor,
so it ships switched off (``enabled = false``).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MIN_WINDOW_MONTHS = 6
SENSITIVITY_WINDOWS = (12, 18, 24, 36)


@dataclass(frozen=True)
class RegimeSplice:
    """Configuration of the splice.

    Attributes
    ----------
    enabled : bool
        Apply the splice. Off by default so the refactor stays equivalent.
    break_month : str
        First month of the anchored regime (``YYYY-MM``).
    window_months : int
        Months on each side of the break used to estimate it.
    """

    enabled: bool = False
    break_month: str = "2001-01"
    window_months: int = 24

    def __post_init__(self) -> None:
        if not _MONTH.match(self.break_month):
            raise ValueError(f"break_month must be YYYY-MM, got {self.break_month!r}")
        if self.window_months < MIN_WINDOW_MONTHS:
            raise ValueError(f"window_months must be at least {MIN_WINDOW_MONTHS}")

    @classmethod
    def from_toml(cls, path: Path) -> RegimeSplice:
        """Load the configuration; a missing file means the splice is off."""
        path = Path(path)
        if not path.is_file():
            return cls()
        section = tomllib.loads(path.read_text(encoding="utf-8")).get("regime_splice", {})
        unknown = set(section) - {"enabled", "break_month", "window_months"}
        if unknown:
            raise ValueError(f"Unknown regime_splice keys: {sorted(unknown)}")
        return cls(**section)


@dataclass(frozen=True)
class BreakEstimate:
    """The level break of one series, in rate units (a proportion)."""

    delta: float
    std_error: float
    std_error_autocorrelation_adjusted: float
    residual_autocorrelation: float
    slope_per_month: float
    diff_of_means: float
    window_months: int

    def as_dict(self) -> dict:
        return {name: float(value) for name, value in self.__dict__.items()}


def estimate_break(rates: pd.Series, break_month: str, window_months: int) -> BreakEstimate:
    """Estimate the level break of a monthly series at ``break_month``.

    Fits ``rate = a + b*k + delta*post`` over ``window_months`` months on each
    side (``k`` months from the break, ``post`` 1 from the break on). ``delta``
    is the level the series gains at the break once the common trend is
    removed.

    Parameters
    ----------
    rates : pandas.Series
        Rates indexed by ``YYYY-MM``.
    break_month : str
        First month of the anchored regime.
    window_months : int
        Months on each side of the break.

    Raises
    ------
    ValueError
        If the series does not have the window on both sides, or has gaps.
    """
    series = rates.sort_index()
    periods = list(series.index)
    if break_month not in periods:
        raise ValueError(f"{break_month} is not in the series")
    cut = periods.index(break_month)
    if cut < window_months or len(periods) - cut < window_months:
        raise ValueError(
            f"Window of {window_months} months does not fit around {break_month} "
            f"({cut} months before, {len(periods) - cut} from the break on)"
        )
    window = series.iloc[cut - window_months : cut + window_months]
    if window.isna().any() or not np.isfinite(window.to_numpy(float)).all():
        raise ValueError("The estimation window has missing values")
    months = np.arange(-window_months, window_months, dtype=float)
    post = (months >= 0).astype(float)
    design = np.column_stack([np.ones_like(months), months, post])
    y = window.to_numpy(float)
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ beta
    degrees = len(y) - design.shape[1]
    covariance = (residual @ residual / degrees) * np.linalg.inv(design.T @ design)
    se = float(np.sqrt(covariance[2, 2]))
    rho = float(np.corrcoef(residual[:-1], residual[1:])[0, 1]) if residual.std() > 0 else 0.0
    inflation = float(np.sqrt((1 + rho) / (1 - rho))) if 0 < rho < 0.99 else 1.0
    return BreakEstimate(
        delta=float(beta[2]),
        std_error=se,
        std_error_autocorrelation_adjusted=se * inflation,
        residual_autocorrelation=rho,
        slope_per_month=float(beta[1]),
        diff_of_means=float(window.iloc[window_months:].mean() - window.iloc[:window_months].mean()),
        window_months=window_months,
    )


def _sensitivity(rates: pd.Series, config: RegimeSplice) -> dict[int, float]:
    out: dict[int, float] = {}
    for window in SENSITIVITY_WINDOWS:
        try:
            out[window] = estimate_break(rates, config.break_month, window).delta
        except ValueError:
            continue
    return out


def _by(frame: pd.DataFrame, key: str, rate: str) -> dict[str, pd.Series]:
    return {str(code): group.set_index("period")[rate] for code, group in frame.groupby(key)}


def _check_bounds(values: pd.Series, what: str) -> None:
    if not values.between(0, 1).all():
        raise ValueError(f"The splice would push {what} outside [0, 1]")


def splice_regime(
    *,
    national: pd.DataFrame,
    cities: pd.DataFrame,
    priors: pd.DataFrame,
    departments: pd.DataFrame,
    config: RegimeSplice,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Shift the unobserved segment of every series to the anchored regime.

    Parameters
    ----------
    national : pandas.DataFrame
        The national sequence (``informality_rate_estimated`` by ``national_type``).
    cities : pandas.DataFrame
        The city sequence (``informality_rate`` by ``city_code``).
    priors : pandas.DataFrame
        Department priors (``prior_rate`` by ``dep_code``), shifted so the
        calibrated departments are continuous at the break.
    departments : pandas.DataFrame
        Departments calibrated *without* the splice (``informality_rate``);
        their breaks are the ones the priors are corrected by.
    config : RegimeSplice
        The enabled configuration.

    Returns
    -------
    tuple
        ``(national, cities, priors, report)``; the inputs are not modified.
        Rows from ``break_month`` on are returned unchanged.
    """
    if not config.enabled:
        raise ValueError("splice_regime called with the splice disabled")
    cut = config.break_month
    reference = national[national.national_type.eq("ICML_COMPLETO")]
    national_series = reference.set_index("period")["informality_rate_estimated"]
    national_break = estimate_break(national_series, cut, config.window_months)
    department_breaks = {
        code: estimate_break(series, cut, config.window_months)
        for code, series in _by(departments, "dep_code", "informality_rate").items()
    }
    city_breaks = {
        code: estimate_break(series, cut, config.window_months)
        for code, series in _by(cities, "city_code", "informality_rate").items()
    }

    new_national = national.copy()
    before = new_national.period < cut
    new_national.loc[before, "informality_rate_estimated"] += national_break.delta
    new_national["informal_estimated"] = np.where(
        before,
        new_national.employed_frozen * new_national.informality_rate_estimated,
        new_national.informal_estimated,
    )
    new_national["formal_estimated"] = np.where(
        before,
        new_national.employed_frozen - new_national.informal_estimated,
        new_national.formal_estimated,
    )
    _check_bounds(new_national.informality_rate_estimated, "the national rate")

    new_priors = priors.copy()
    shift = new_priors.dep_code.astype(str).map({c: e.delta for c, e in department_breaks.items()})
    new_priors["prior_rate"] = np.where(new_priors.period < cut, new_priors.prior_rate + shift, new_priors.prior_rate)
    _check_bounds(new_priors.prior_rate, "a department prior")

    new_cities = cities.copy()
    city_shift = new_cities.city_code.astype(str).map({c: e.delta for c, e in city_breaks.items()})
    pre_city = new_cities.period < cut
    new_cities["informality_rate"] = np.where(pre_city, new_cities.informality_rate + city_shift, new_cities.informality_rate)
    new_cities["informal_estimated"] = np.where(
        pre_city, new_cities.employed_frozen * new_cities.informality_rate, new_cities.informal_estimated
    )
    new_cities["formal_estimated"] = np.where(
        pre_city, new_cities.employed_frozen - new_cities.informal_estimated, new_cities.formal_estimated
    )
    _check_bounds(new_cities.informality_rate, "a city rate")

    report = {
        "break_month": cut,
        "window_months": config.window_months,
        "method": "regression discontinuity with a common slope; unobserved segment shifted by a constant",
        "months_shifted": int(before.sum() // national.national_type.nunique()),
        "national": national_break.as_dict(),
        "national_sensitivity_by_window": {str(k): v for k, v in _sensitivity(national_series, config).items()},
        "departments": {code: est.delta for code, est in sorted(department_breaks.items())},
        "cities": {code: est.delta for code, est in sorted(city_breaks.items())},
    }
    return new_national, new_cities, new_priors, report
