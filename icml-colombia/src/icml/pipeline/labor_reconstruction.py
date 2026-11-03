"""Restoration of the 1993-2000 labor reconstruction: a linear PET and generated components.

The monthly series before the first GEIH month are a reconstruction. Two properties of that
reconstruction were lost when the stages were migrated, and this module restores them, following the
author's original national estimation (``1 - Estimación Nacional.ipynb``, sections 2.7 and 2.8):

1. **The working-age population (PET) is a straight line.** It is a demographic projection, so it
   cannot go up and down: it runs in a straight line from its level at the start of the history (the
   median of the first year) to the official value of the first GEIH month. The stage treatment
   (ADR-006, minimum curvature that keeps the eight annual survey means) leaves bumps, because the
   annual means of the old survey are not collinear.
2. **The components of the rates are generated.** The reconstructed rates are far smoother than the
   observed ones (the monthly change of the unemployment rate is five times smaller). The original
   method gives the history the dynamics of the GEIH era: it fits the irregular component of the
   official rates (STL), adds deterministic noise scaled by ``scaling_factor``, and replaces the
   seasonal pattern by the 2001-2018 one.

How it works, for the national reference series:

* the rates TO (employment/PET) and TD (unemployment/PEA) are kept and the levels rebuilt on the
  linear PET: ``employed = TO * PET``, ``PEA = employed / (1 - TD)``, ``unemployed = PEA - employed``,
  ``inactive = PET - PEA``;
* noise is added to TO and TD (seeded by the period, so a month always gets the same noise);
* the seasonal component of ``employed`` and ``unemployed`` is replaced by the reference one,
  keeping their STL trend and irregular parts; ``PEA = employed + unemployed`` and
  ``inactive = PET - PEA`` close the accounting.

The original notebook injected noise into TGP too and swapped the seasonal part of PEA and inactive
separately, which left ``PEA - (employed + unemployed)`` off by up to 357,000 persons. Here PEA is the
sum and inactive the remainder, so **every identity holds exactly**; TGP is implied by the other two
rates.

The same method runs on every series with its own official months: the national reference with the
national ones, each department and each city with theirs (each territory gets the seasonal pattern and the
irregular scale it really has, and its own linear PET). The national ICML series is the sum of the
departments. From the first official month on the national series do not change; the territories only change in
their PET, population and inactive (see ``smooth_territories``).

After the first official month the national series are official and stay as they are, but the PET and the
population of the territories are not necessarily smooth (a department's monthly PET zig-zags) and should be,
like the national ones. With ``smooth_territories`` each department's share of the national total is smoothed
by a minimum-curvature curve that keeps its annual means (one linear operator for all, so the 33 shares still
add to one and the departments still add to the national figure exactly); a city's own level is smoothed the
same way. Employed, unemployed and the labor force do not change: inactive absorbs the PET. The line before
the first official month then ends at the smoothed value of that month.

It replaces the PET base splice (``labor_base_splice``): the line anchored at the official value already
closes the seam that splice estimated, and running both would shift the start of the line. It is a
methodological change, not part of the equivalence refactor.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import splu
from statsmodels.tsa.seasonal import STL

LEVELS = ("employed", "unemployed", "labor_force", "inactive", "working_age")
REPRESENTED = tuple(f"{level}_represented" for level in (*LEVELS, "population"))
#: What smoothing the official territorial months may change: the denominators and what absorbs them.
SMOOTHED = ("working_age", "population", "inactive")
FACTORS = tuple(f"factor_{level}" for level in (*LEVELS, "population"))
RATE_COLUMNS = {
    "unemployment_rate": ("unemployed", "labor_force"),
    "employment_rate": ("employed", "working_age"),
    "participation_rate": ("labor_force", "working_age"),
}
FILES = ("departamentos", "ciudades", "nacionales")
REFERENCE = "DANE_REFERENCIA"
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_IDENTITY_TOLERANCE = 1e-6


class ReconstructionError(ValueError):
    """The restoration would break an accounting identity or protected values."""


@dataclass(frozen=True)
class LaborReconstruction:
    """Configuration of the restoration.

    Attributes
    ----------
    enabled : bool
        Apply it. Off by default so the refactor stays equivalent.
    splice_month : str
        First official month (``YYYY-MM``): the anchor of the line and the end of the history.
    scaling_factor : float
        Amplitude of the generated noise, as a share of the irregular component of the official rates.
    base_seed : int
        Base of the deterministic seed (one seed per period).
    stl_period, stl_seasonal : int
        STL period (12 = monthly) and seasonal smoother length (odd).
    stl_robust : bool
        Robust STL (down-weights outliers).
    reference_first_year, reference_last_year : int
        Official years whose seasonal pattern replaces the reconstructed one.
    floor_share : float
        A level can never fall below this share of what it was before the seasonal swap (guards the
        smallest territories, whose pattern can be larger than their level).
    linearize_population : bool
        Also draw the total population as a line before the first official month (the original notebook did).
    smooth_territories : bool
        Smooth the PET and the population of the departments and cities after the first official month.
    """

    enabled: bool = False
    splice_month: str = "2001-01"
    scaling_factor: float = 0.45
    base_seed: int = 42
    stl_period: int = 12
    stl_seasonal: int = 13
    stl_robust: bool = True
    reference_first_year: int = 2001
    reference_last_year: int = 2018
    floor_share: float = 0.05
    linearize_population: bool = False
    smooth_territories: bool = False

    def __post_init__(self) -> None:
        if not _MONTH.match(self.splice_month):
            raise ValueError(f"splice_month must be YYYY-MM, got {self.splice_month!r}")
        if not 0 <= self.scaling_factor <= 1:
            raise ValueError("scaling_factor must be in [0, 1]")
        if self.stl_period < 2 or self.stl_seasonal < 3 or self.stl_seasonal % 2 == 0:
            raise ValueError("stl_period must be >= 2 and stl_seasonal an odd number >= 3")
        if self.reference_first_year > self.reference_last_year:
            raise ValueError("reference_first_year must not exceed reference_last_year")
        if not 0 < self.floor_share < 1:
            raise ValueError("floor_share must be in (0, 1)")

    @classmethod
    def from_toml(cls, path: Path) -> LaborReconstruction:
        """Load the configuration; a missing file means the restoration is off."""
        path = Path(path)
        if not path.is_file():
            return cls()
        section = tomllib.loads(path.read_text(encoding="utf-8")).get("labor_reconstruction", {})
        unknown = set(section) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown labor_reconstruction keys: {sorted(unknown)}")
        return cls(**section)


@dataclass(frozen=True)
class Template:
    """Irregular component of an official rate (what the noise is scaled to)."""

    rate: str
    irregularity_std: float
    extremes_pct95: float
    autocorrelation_lag1: float
    observations: int

    def as_dict(self) -> dict:
        return {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in self.__dict__.items()}


# ------------------------------------------------------------------------------------ building blocks


def linear_path(start: float, anchor: float, months: int) -> np.ndarray:
    """``months`` values on the straight line from ``start`` to ``anchor``; the anchor itself comes after.

    The line keeps one slope across the first official month: its value there is ``anchor``.
    """
    return np.linspace(start, anchor, months, endpoint=False)


def _stl(values: np.ndarray, config: LaborReconstruction):
    return STL(values, period=config.stl_period, seasonal=config.stl_seasonal, robust=config.stl_robust).fit()


def fit_templates(official: pd.DataFrame, config: LaborReconstruction) -> dict[str, Template]:
    """STL irregular component of the official TO and TD (and TGP, for the record)."""
    rates = {
        "to": official["employed"] / official["working_age"],
        "td": official["unemployed"] / official["labor_force"],
        "tgp": official["labor_force"] / official["working_age"],
    }
    out = {}
    for name, series in rates.items():
        values = series.to_numpy(float)
        if len(values) < 2 * config.stl_period or not np.isfinite(values).all():
            raise ReconstructionError(f"The official series of {name} is too short or not finite for STL")
        irregular = _stl(values, config).resid
        out[name] = Template(
            name,
            float(np.std(irregular)),
            float(np.percentile(np.abs(irregular), 95)),
            float(np.corrcoef(irregular[:-1], irregular[1:])[0, 1]),
            len(values),
        )
    return out


def period_noise(period: str, template: Template, config: LaborReconstruction, salt: str = "") -> float:
    """Noise of one period: the same value in every run, whatever the order or the other periods.

    The seed is ``base_seed`` plus the MD5 of ``YYYY-MM`` (as in the original notebook; a territory adds
    its code so the territories do not share one draw); the draw is Normal(0, std * scaling) clipped to
    +-2.5 * pct95 * scaling.
    """
    key = f"{salt}|{period}" if salt else period
    digest = int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.default_rng((config.base_seed + digest) % (2**31))
    sigma = template.irregularity_std * config.scaling_factor
    bound = 2.5 * template.extremes_pct95 * config.scaling_factor
    return float(np.clip(rng.normal(0.0, sigma), -bound, bound))


def swap_seasonal(
    pre: pd.Series, reference: pd.Series, config: LaborReconstruction
) -> pd.Series:
    """Replace the seasonal component of ``pre`` by the (scaled) calendar pattern of ``reference``.

    ``result = STL trend of pre + STL irregular of pre + reference seasonal pattern * scale`` with
    ``scale = mean(pre) / mean(reference)``, so the pattern has the amplitude that fits the level of
    the reconstructed segment. Both series are indexed by ``YYYY-MM``.
    """
    minimum = 2 * config.stl_period
    if len(pre) < minimum or len(reference) < minimum:
        raise ReconstructionError("The segments are too short for the seasonal swap")
    stl_pre, stl_ref = _stl(pre.to_numpy(float), config), _stl(reference.to_numpy(float), config)
    months_ref = reference.index.str[5:7]
    pattern = pd.Series(stl_ref.seasonal, index=reference.index).groupby(months_ref).mean()
    scale = float(np.abs(pre.to_numpy(float)).mean() / np.abs(reference.to_numpy(float)).mean())
    seasonal = np.array([pattern[m] for m in pre.index.str[5:7]]) * scale
    return pd.Series(stl_pre.trend + stl_pre.resid + seasonal, index=pre.index)


# ------------------------------------------------------------------------------------ one series


def reconstruct_series(
    series: pd.DataFrame, config: LaborReconstruction, salt: str = ""
) -> tuple[pd.DataFrame, dict]:
    """New levels of the months before the first official one, for one series.

    The method of the original notebook with exact accounting: a linear PET, TO and TD kept, noise on
    both, the seasonal component of employment and unemployment replaced by the official pattern, and
    PEA and inactive as the sum and the remainder.

    Parameters
    ----------
    series : pandas.DataFrame
        Indexed by ``YYYY-MM``, sorted, with ``working_age``, ``employed``, ``unemployed``,
        ``labor_force`` and ``inactive`` for the history and the official months.
    config : LaborReconstruction
        The enabled configuration.
    salt : str
        Added to the noise seed (empty for the national series, the territory code otherwise).

    Returns
    -------
    tuple
        ``(levels, details)``: the new levels of the history (same columns) and what the method
        measured (templates, rates before and after, the line, floors applied).
    """
    if config.splice_month not in series.index:
        raise ReconstructionError(f"{config.splice_month} is not in the series")
    pre = series.index < config.splice_month
    official, history = series.loc[~pre], series.loc[pre]
    if len(history) < 2 * config.stl_period:
        raise ReconstructionError("The history is too short for STL")

    months = len(history)
    start = float(history["working_age"].iloc[: config.stl_period].median())
    anchor = float(series.loc[config.splice_month, "working_age"])
    pet = linear_path(start, anchor, months)

    # 1-2. keep TO and TD, rebuild the levels on the linear PET
    to0 = (history["employed"] / history["working_age"]).to_numpy(float)
    td0 = (history["unemployed"] / history["labor_force"]).to_numpy(float).clip(0, 0.99)

    # 3-4. templates from the official months, deterministic noise on TO and TD
    templates = fit_templates(official, config)
    noise_to = np.array([period_noise(p, templates["to"], config, salt) for p in history.index])
    noise_td = np.array([period_noise(p, templates["td"], config, salt) for p in history.index])
    to1 = (to0 + noise_to).clip(0, 1)
    td1 = (td0 + noise_td).clip(0, 0.99)
    employed = to1 * pet
    pea = employed / (1.0 - td1)
    unemployed = pea - employed

    # 5. seasonal swap on employed and unemployed; PEA and inactive close the accounting
    years = official.index.str[:4].astype(int)
    reference = official[(years >= config.reference_first_year) & (years <= config.reference_last_year)]
    floors = 0
    swapped = {}
    for name, values in (("employed", employed), ("unemployed", unemployed)):
        corrected = swap_seasonal(pd.Series(values, index=history.index), reference[name], config)
        floor = config.floor_share * pd.Series(values, index=history.index)
        floors += int((corrected < floor).sum())
        swapped[name] = np.maximum(corrected, floor)  # a tiny territory can have a pattern larger than its level
    pea_s = swapped["employed"] + swapped["unemployed"]
    inactive = pd.Series(pet, index=history.index) - pea_s
    if (inactive < -_IDENTITY_TOLERANCE).any():
        raise ReconstructionError("The labor force would exceed the working-age population")

    levels = pd.DataFrame(
        {
            "working_age": pet,
            "employed": swapped["employed"].to_numpy(),
            "unemployed": swapped["unemployed"].to_numpy(),
            "labor_force": pea_s.to_numpy(),
            "inactive": inactive.to_numpy(),
        },
        index=history.index,
    )
    details = {
        "start_pet": start,
        "anchor_pet": anchor,
        "monthly_slope": float((anchor - start) / months),
        "months": months,
        "floors_applied": floors,
        "templates": {k: v.as_dict() for k, v in templates.items()},
        "rates_before": {"to": pd.Series(to0, index=history.index), "td": pd.Series(td0, index=history.index)},
        "rates_after": {
            "to": levels["employed"] / levels["working_age"],
            "td": levels["unemployed"] / levels["labor_force"],
            "tgp": levels["labor_force"] / levels["working_age"],
        },
    }
    return levels, details


# ------------------------------------------------------------------------------------ smoothing


def smooth_annual_means(values: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Minimum-curvature curves that keep the annual mean of every column.

    Minimizes the squared second difference subject to each calendar year having the mean it had. The
    solution is linear in the data and maps a constant to itself, so smoothing shares that add to one gives
    shares that add to one. A trend that is already a line comes back unchanged.

    Parameters
    ----------
    values : numpy.ndarray
        ``months x series``.
    years : numpy.ndarray
        Calendar year of each month (a partial last year is allowed).
    """
    values = np.asarray(values, float)
    months = len(years)
    unique = sorted(set(years.tolist()))
    if months < 6 or len(unique) < 2:
        raise ReconstructionError("Smoothing needs at least two years")
    rows, columns, weights = [], [], []
    for position, year in enumerate(unique):
        index = np.flatnonzero(years == year)
        rows += [position] * len(index)
        columns += index.tolist()
        weights += [1.0 / len(index)] * len(index)
    annual = sparse.csr_matrix((weights, (rows, columns)), shape=(len(unique), months))
    second = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(months - 2, months), format="csr")
    system = sparse.bmat([[(2 * (second.T @ second)).tocsc(), annual.T], [annual, None]], format="csc")
    rhs = np.vstack([np.zeros_like(values), annual @ values])
    return splu(system).solve(rhs)[:months]


def smooth_territories(
    departments: pd.DataFrame, cities: pd.DataFrame, config: LaborReconstruction
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Smooth the PET and the population of the territories from the first official month on.

    Departments: the share of each one in the total (the sum of the 33 is the national ICML figure) is
    smoothed and multiplied back, so the sum is untouched; when the represented universe exists, in two constant
    groups (the always fully represented territories and the rest) so the sums of the represented universe stay too. Cities: their own level. Inactive is the PET
    minus the labor force; employed, unemployed and the labor force are not touched.

    Returns
    -------
    tuple
        ``(departments, cities, stats)`` with new frames (the inputs are not modified).
    """
    cut = config.splice_month
    out_departments, out_cities = departments.copy(), cities.copy()
    stats: dict = {}
    for column in ("working_age", "population"):
        post = departments[departments["period"] >= cut]
        wide = post.pivot(index="period", columns="dep_code", values=column).sort_index()
        years = np.array([int(p[:4]) for p in wide.index])
        represented_column = f"{column}_represented"
        represented = None
        groups = [list(wide.columns)]
        if represented_column in departments.columns:
            # Two constant groups: the territories the GEIH represents completely in every month, and the rest. The
            # split between the groups is smoothed first (the rest carries nearly all the zig-zag), then each group
            # inside. A fully represented territory takes the smoothed value (its factor stays exactly one) and a
            # partly represented one absorbs its own change, so while every territory is at least partly
            # represented the represented universe still adds up to what it did.
            represented = post.pivot(index="period", columns="dep_code", values=represented_column).sort_index()
            if (represented > wide + 1e-6).any().any():
                raise ReconstructionError(f"The represented {column} exceeds the full one")
            complete = [c for c in wide.columns if (represented[c] >= wide[c] - 1e-6).all()]
            groups = [g for g in (complete, [c for c in wide.columns if c not in complete]) if g]
        new = wide.copy()
        totals = pd.DataFrame({i: wide[g].sum(axis=1) for i, g in enumerate(groups)})
        if len(groups) > 1:
            split = smooth_annual_means(totals.div(totals.sum(axis=1), axis=0).to_numpy(), years)
            split = split / split.sum(axis=1, keepdims=True)
            if (split <= 0).any():
                raise ReconstructionError(f"Smoothing the split of the {column} between groups gave non-positive values")
            totals = pd.DataFrame(split * totals.sum(axis=1).to_numpy()[:, None], index=totals.index, columns=totals.columns)
        for i, group in enumerate(groups):
            members = wide[group]
            smooth = smooth_annual_means((members.div(members.sum(axis=1), axis=0)).to_numpy(), years)
            smooth = smooth / smooth.sum(axis=1, keepdims=True)
            new[group] = smooth * totals[i].to_numpy()[:, None]
        if represented is not None:
            new_represented = represented.copy()
            rest = [c for c in wide.columns if c not in complete]
            for c in complete:
                new_represented[c] = new[c]
            for c in rest:
                shifted = represented[c] + (new[c] - wide[c])
                new_represented[c] = shifted.where(represented[c] > 0, 0.0)
            if (new_represented < -1e-6).any().any() or (new_represented > new + 1e-6).any().any():
                raise ReconstructionError(f"Smoothing the {column} left a represented value outside [0, full]")
            new_represented = new_represented.clip(lower=0.0)
            keys = pd.MultiIndex.from_frame(out_departments.loc[out_departments["period"] >= cut, ["period", "dep_code"]])
            rows = out_departments["period"] >= cut
            out_departments.loc[rows, represented_column] = new_represented.stack().reindex(keys).to_numpy()
        total = wide.sum(axis=1)
        if (new <= 0).any().any() and (wide > 0).all().all():
            raise ReconstructionError(f"Smoothing the {column} gave non-positive values")
        keys = pd.MultiIndex.from_frame(out_departments.loc[out_departments["period"] >= cut, ["period", "dep_code"]])
        rows = out_departments["period"] >= cut
        out_departments.loc[rows, column] = new.stack().reindex(keys).to_numpy()
        change = ((new - wide).abs() / wide.where(wide > 0)).fillna(0.0)
        stats[column] = {
            "departments_max_change_pct": float(100 * change.to_numpy().max()),
            "departments_median_direction_changes_before": float(np.median((np.diff(np.sign(np.diff(wide.to_numpy(), axis=0)), axis=0) != 0).sum(axis=0))),
            "departments_median_direction_changes_after": float(np.median((np.diff(np.sign(np.diff(new.to_numpy(), axis=0)), axis=0) != 0).sum(axis=0))),
            "departments_max_annual_mean_change_pct": float(100 * ((new.groupby(years).mean() - wide.groupby(years).mean()).abs() / wide.groupby(years).mean().where(wide.groupby(years).mean() > 0)).fillna(0.0).to_numpy().max()),
            "sum_error_persons": float((new.sum(axis=1) - total).abs().max()),
        }
        post_cities = cities[cities["period"] >= cut]
        wide_c = post_cities.pivot(index="period", columns="city_code", values=column).sort_index()
        scale = wide_c.median()
        smooth_c = smooth_annual_means((wide_c / scale).to_numpy(), years) * scale.to_numpy()
        if (smooth_c <= 0).any():
            raise ReconstructionError(f"Smoothing the {column} of the cities gave non-positive values")
        new_c = pd.DataFrame(smooth_c, index=wide_c.index, columns=wide_c.columns)
        rows_c = out_cities["period"] >= cut
        keys_c = pd.MultiIndex.from_frame(out_cities.loc[rows_c, ["period", "city_code"]])
        out_cities.loc[rows_c, column] = new_c.stack().reindex(keys_c).to_numpy()
        stats[column]["cities_max_change_pct"] = float(100 * (new_c / wide_c - 1).abs().to_numpy().max())
    post_rows = out_departments["period"] >= cut
    if {"inactive_represented", "working_age_represented", "labor_force_represented"} <= set(out_departments.columns):
        out_departments.loc[post_rows, "inactive_represented"] = (
            out_departments.loc[post_rows, "working_age_represented"] - out_departments.loc[post_rows, "labor_force_represented"]
        )
    out_departments.loc[post_rows, "inactive"] = out_departments.loc[post_rows, "working_age"] - out_departments.loc[post_rows, "labor_force"]
    for base in SMOOTHED:
        factor, represented_column = f"factor_{base}", f"{base}_represented"
        if factor in out_departments.columns and represented_column in out_departments.columns:
            full = out_departments.loc[post_rows, base]
            out_departments.loc[post_rows, factor] = np.where(full > 0, out_departments.loc[post_rows, represented_column] / full.where(full > 0), 0.0)
    if "inactive_represented" in out_departments.columns and (out_departments.loc[post_rows, "inactive_represented"] < -_IDENTITY_TOLERANCE).any():
        raise ReconstructionError("Smoothing left a represented territory with a labor force above its working-age population")
    for frame in (out_departments, out_cities):
        rows = frame["period"] >= cut
        frame.loc[rows, "inactive"] = frame.loc[rows, "working_age"] - frame.loc[rows, "labor_force"]
        if (frame.loc[rows, "inactive"] <= 0).any():
            raise ReconstructionError("Smoothing the PET left a territory with a labor force above its working-age population")
        if (frame.loc[rows, "working_age"] > frame.loc[rows, "population"]).any():
            raise ReconstructionError("Smoothing left a territory with a PET above its population")
    return out_departments, out_cities, stats


# ------------------------------------------------------------------------------------ frames


def require_exclusive_with_base_splice(base_splice_enabled: bool, reconstruction: LaborReconstruction) -> None:
    """Refuse to run the PET base splice and this restoration together.

    The line anchored at the first official month already closes the seam the splice estimates, and the
    splice would shift the level the line starts from.
    """
    if base_splice_enabled and reconstruction.enabled:
        raise ValueError(
            "labor_base_splice and labor_reconstruction are mutually exclusive: the linear PET anchored at the "
            "first official month replaces the PET base splice"
        )


def _require(frame: pd.DataFrame, what: str) -> None:
    missing = {"period", "population", *LEVELS} - set(frame.columns)
    if missing:
        raise ReconstructionError(f"{what} lacks columns {sorted(missing)}")


def _refresh_rates(frame: pd.DataFrame, mask: pd.Series, only: tuple[str, ...] | None = None) -> None:
    for column, (top, bottom) in RATE_COLUMNS.items():
        if column in frame.columns and (only is None or column in only):
            frame.loc[mask, column] = frame.loc[mask, top] / frame.loc[mask, bottom]


def reconstruct_frames(
    departments: pd.DataFrame, cities: pd.DataFrame, national: pd.DataFrame, config: LaborReconstruction
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Restore the linear PET and the generated components in the three numeric labor tables.

    Parameters
    ----------
    departments, cities, national : pandas.DataFrame
        The labor products with numeric levels; ``national`` has ``national_type``
        (``ICML_COMPLETO`` and ``DANE_REFERENCIA``).
    config : LaborReconstruction
        The enabled configuration.

    Returns
    -------
    tuple
        ``(departments, cities, national, report)``. The inputs are not modified and every row from the
        splice month on is returned unchanged.
    """
    if not config.enabled:
        raise ValueError("reconstruct_frames called with the restoration disabled")
    cut = config.splice_month
    for frame, what in ((departments, "departments"), (cities, "cities"), (national, "national")):
        _require(frame, what)

    original = (departments, cities, national)
    smoothing = None
    if config.smooth_territories:
        # first: the line before the first official month must end at the smoothed value of that month
        departments, cities, smoothing = smooth_territories(departments, cities, config)
    reference = national[national["national_type"] == REFERENCE].set_index("period").sort_index()
    new_levels, details = reconstruct_series(reference, config)

    out_departments, out_cities, out_national = departments.copy(), cities.copy(), national.copy()
    pet_lines: dict[str, dict] = {}
    floors = {"national": details["floors_applied"], "departments": 0, "cities": 0}
    for frame, key, label, target in (
        (departments, "dep_code", "departments", out_departments),
        (cities, "city_code", "cities", out_cities),
    ):
        for code, group in frame.groupby(key, sort=True):
            series = group.set_index("period").sort_index()
            rebuilt, own = reconstruct_series(series, config, salt=f"{label[:3]}:{code}")
            floors[label] += own["floors_applied"]
            rows = (target[key] == code) & (target["period"] < cut)
            order = target.loc[rows, "period"]
            for level in LEVELS:
                target.loc[rows, level] = rebuilt[level].reindex(order).to_numpy()
            pet_lines.setdefault(label, {})[str(code)] = {"start": own["start_pet"], "anchor": own["anchor_pet"]}
    details["floors_by_level"] = floors
    pre_departments = out_departments["period"] < cut
    post_departments = ~pre_departments
    if config.linearize_population:
        for frame, key, target in ((departments, "dep_code", out_departments), (cities, "city_code", out_cities)):
            for code, group in frame.groupby(key, sort=True):
                series = group.set_index("period").sort_index()
                history = series.loc[series.index < cut]
                line = linear_path(float(history["population"].iloc[: config.stl_period].median()), float(series.loc[cut, "population"]), len(history))
                rows = (target[key] == code) & (target["period"] < cut)
                target.loc[rows, "population"] = pd.Series(line, index=history.index).reindex(target.loc[rows, "period"]).to_numpy()

    # the represented universe follows the full one (after the lines and the smoothing changed the full levels)
    for level in REPRESENTED:
        base = level.removesuffix("_represented")
        factor = f"factor_{base}"
        if level not in out_departments.columns or factor not in out_departments.columns:
            continue
        # after the first official month the smoothing already set the represented levels and their factors
        out_departments.loc[pre_departments, level] = out_departments.loc[pre_departments, factor] * out_departments.loc[pre_departments, base]

    # national: the reference gets the national result, ICML is the sum of the departments
    is_reference = (out_national["national_type"] == REFERENCE) & (out_national["period"] < cut)
    order = out_national.loc[is_reference, "period"]
    for level in LEVELS:
        out_national.loc[is_reference, level] = new_levels[level].reindex(order).to_numpy()
    sums = out_departments[out_departments["period"] < cut].groupby("period")[list(LEVELS)].sum()
    is_icml = (out_national["national_type"] == "ICML_COMPLETO") & (out_national["period"] < cut)
    order = out_national.loc[is_icml, "period"]
    for level in LEVELS:
        out_national.loc[is_icml, level] = sums[level].reindex(order).to_numpy()
    if config.linearize_population:
        population = out_departments[out_departments["period"] < cut].groupby("period")["population"].sum()
        out_national.loc[is_icml, "population"] = population.reindex(order).to_numpy()
        history = reference.loc[reference.index < cut, "population"]
        line = linear_path(float(history.iloc[: config.stl_period].median()), float(reference.loc[cut, "population"]), len(history))
        out_national.loc[is_reference, "population"] = pd.Series(line, index=history.index).reindex(order).to_numpy()
    _refresh_rates(out_departments, pre_departments)
    _refresh_rates(out_national, out_national["period"] < cut)
    if config.smooth_territories:
        _refresh_rates(out_departments, post_departments, only=("employment_rate", "participation_rate"))

    report = _validate(*original, out_departments, out_cities, out_national, config, details)
    report["pet_lines"] = pet_lines
    if smoothing is not None:
        report["smoothing"] = smoothing
    return out_departments, out_cities, out_national, report


def _identity(frame: pd.DataFrame, mask: pd.Series) -> tuple[float, float]:
    rows = frame[mask]
    return (
        float((rows["labor_force"] - rows["employed"] - rows["unemployed"]).abs().max()),
        float((rows["working_age"] - rows["labor_force"] - rows["inactive"]).abs().max()),
    )


def _validate(old_dep, old_cit, old_nat, dep, cit, nat, config: LaborReconstruction, details: dict) -> dict:
    """Identities, bounds and untouched rows; raises if anything protected moved."""
    cut = config.splice_month
    territorial_allowed = {
        *SMOOTHED, "employment_rate", "participation_rate",
        *(f"{c}_represented" for c in SMOOTHED), *(f"factor_{c}" for c in SMOOTHED),
    } if config.smooth_territories else set()
    for before, after, what in ((old_dep, dep, "departments"), (old_cit, cit, "cities"), (old_nat, nat, "national")):
        official = before["period"] >= cut
        allowed = territorial_allowed if what != "national" else set()
        columns = [c for c in before.columns if pd.api.types.is_numeric_dtype(before[c]) and c not in allowed]
        if not np.array_equal(before.loc[official, columns].to_numpy(float), after.loc[official, columns].to_numpy(float), equal_nan=True):
            raise ReconstructionError(f"The restoration changed an official month of {what}")
    residuals = {}
    for frame, what in ((dep, "departments"), (cit, "cities"), (nat, "national")):
        mask = frame["period"] < cut
        pea, pet = _identity(frame, mask)
        residuals[what] = {"labor_force": pea, "working_age": pet}
        if max(pea, pet) > _IDENTITY_TOLERANCE * max(1.0, float(frame.loc[mask, "working_age"].max())):
            raise ReconstructionError(f"An accounting identity of {what} does not close ({max(pea, pet):.3g} persons)")
        rows = frame[mask]
        if (rows[list(LEVELS)] < -_IDENTITY_TOLERANCE).any().any():
            raise ReconstructionError(f"{what} has negative levels")
    official_checks = {}
    if config.smooth_territories:
        icml = nat[(nat["national_type"] == "ICML_COMPLETO") & (nat["period"] >= cut)].set_index("period").sort_index()
        sums = dep[dep["period"] >= cut].groupby("period")[["employed", "inactive", "working_age", "population"]].sum().sort_index()
        gap = max(float((sums[c] - icml[c]).abs().max()) for c in sums.columns)
        if gap > 1e-4:
            raise ReconstructionError(f"After smoothing the departments no longer add to the national figure ({gap:.3g} persons)")
        official_checks["departments_vs_national_max_gap_persons"] = gap
        # While every territory is at least partly represented the represented universe adds up to the national GEIH
        # figure and must not change; while some territory is outside it, the sum is informational and may move a little.
        old_official = old_dep[old_dep["period"] >= cut]
        covered = old_official.assign(inside=old_official["population_represented"] > 0).groupby("period")["inside"].all()
        for column in ("working_age_represented", "population_represented"):
            if column in dep.columns:
                change = (dep[dep["period"] >= cut].groupby("period")[column].sum() - old_official.groupby("period")[column].sum()).abs()
                exact = float(change[covered].max()) if covered.any() else 0.0
                if exact > 1e-4:
                    raise ReconstructionError(f"After smoothing the represented {column} no longer adds up as before ({exact:.3g} persons)")
                official_checks[f"{column}_sum_change_persons_all_represented"] = exact
                official_checks[f"{column}_sum_change_persons_some_outside"] = float(change[~covered].max()) if (~covered).any() else 0.0
    after = details["rates_after"]
    before = details["rates_before"]
    icml_old = old_nat[(old_nat["national_type"] == "ICML_COMPLETO") & (old_nat["period"] < cut)].set_index("period").sort_index()
    icml_new = nat[(nat["national_type"] == "ICML_COMPLETO") & (nat["period"] < cut)].set_index("period").sort_index()

    def volatility(frame: pd.DataFrame) -> dict[str, float]:
        return {
            "to": float(100 * (frame["employed"] / frame["working_age"]).diff().std()),
            "td": float(100 * (frame["unemployed"] / frame["labor_force"]).diff().std()),
        }

    return {
        "official_months_checks": official_checks,
        "floors_applied": details["floors_by_level"],
        "splice_month": cut,
        "scaling_factor": config.scaling_factor,
        "base_seed": config.base_seed,
        "months_rebuilt": details["months"],
        "pet_national": {"start": details["start_pet"], "anchor": details["anchor_pet"], "monthly_slope": details["monthly_slope"]},
        "templates": details["templates"],
        "accounting_residual_max_persons": residuals,
        "monthly_change_std_pp": {
            "reference": {
                "before": {k: float(100 * v.diff().std()) for k, v in before.items()},
                "after": {k: float(100 * after[k].diff().std()) for k in ("to", "td")},
            },
            "icml": {"before": volatility(icml_old), "after": volatility(icml_new)},
        },
    }


# ------------------------------------------------------------------------------------ files


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = frame.copy()
    columns = ("population", *LEVELS, *(c for c in (*REPRESENTED, *RATE_COLUMNS, *FACTORS) if c in frame.columns))
    for column in columns:
        numeric[column] = pd.to_numeric(frame[column], errors="raise")
    return numeric


def reconstruct_labor_products(directory: Path, config: LaborReconstruction) -> dict:
    """Apply the restoration in place to the three labor product files.

    Only the cells that change are rewritten (every other cell keeps its exact text), so from the first
    official month on the files are byte for byte what they were. A report is written beside the
    folder as ``labor_reconstruction.json``.

    Parameters
    ----------
    directory : Path
        Folder with ``departamentos.csv``, ``ciudades.csv`` and ``nacionales.csv``.
    config : LaborReconstruction
        The enabled configuration.
    """
    directory = Path(directory)
    text = {name: pd.read_csv(directory / f"{name}.csv", dtype=str, keep_default_na=False) for name in FILES}
    numeric = {name: _numeric(frame) for name, frame in text.items()}
    dep, cit, nat, report = reconstruct_frames(numeric["departamentos"], numeric["ciudades"], numeric["nacionales"], config)
    for name, new in (("departamentos", dep), ("ciudades", cit), ("nacionales", nat)):
        old = numeric[name]
        columns = ("population", *LEVELS, *(c for c in (*REPRESENTED, *RATE_COLUMNS, *FACTORS) if c in old.columns))
        for column in columns:
            changed = ~np.isclose(old[column], new[column], rtol=0, atol=0)
            text[name].loc[changed, column] = [repr(float(v)) for v in new.loc[changed, column]]
        text[name].to_csv(directory / f"{name}.csv", index=False, lineterminator="\n")
    report["files"] = list(FILES)
    (directory.parent / "labor_reconstruction.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
