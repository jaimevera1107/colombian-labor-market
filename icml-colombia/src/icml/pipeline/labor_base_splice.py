"""Splice of the working-age population (PET) share in the labor products.

The labor products have a level break in January 2001: the reconstruction of
1993-2000 (ENH) and the GEIH-based months from 2001 do not agree on the share
of the population that is of working age. That share steps up by about 1.6
points in one month (27 times its normal monthly variation) in the national
series and in all 33 departments, while the population itself and the labor
*rates* (participation, employment, unemployment) show no break of their own.
Splicing the rates would be wrong: around 2000-2001 the unemployment rate turns
with the economic cycle, and a break estimator cannot tell a turning point from
a regime change.

So only the PET share is spliced, and the levels are rebuilt from the rates,
which stay exactly as they are::

    PET'      = (share + delta) * population
    PEA'      = TGP * PET'      employed' = TO * PET'      unemployed' = PEA' - employed'
    inactive' = PET' - PEA'

Every level except the population is multiplied by ``k = (share + delta) /
share``, so every identity and every rate is preserved. The months from the
break on are left untouched.

* Departments: each has its own break (27 of 33 are individually significant).
* National ICML: the sum of the corrected departments, so it still adds up.
* National DANE reference before 2001 (a reconstruction, not official): own break.
* Cities: one common break (the median). Their 1993-2000 values are a
  retropolation of the national series, so they share its shape; individual
  estimates are noisy (8 of 33 significant) and add noise, not information.

A methodological change, not part of the equivalence refactor: off by default.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from icml.informality.regime_splice import RegimeSplice, estimate_break

LEVELS = ("employed", "unemployed", "inactive", "labor_force", "working_age")
REPRESENTED = tuple(f"{level}_represented" for level in LEVELS)
RATE_COLUMNS = {
    "unemployment_rate": ("unemployed", "labor_force"),
    "employment_rate": ("employed", "working_age"),
    "participation_rate": ("labor_force", "working_age"),
}
RATES = tuple(RATE_COLUMNS.values())
#: The national ICML rates are implied by the sum of the departments, so they
#: move a little (a weighted mean with new weights); anything larger is a bug.
NATIONAL_RATE_TOLERANCE = 5e-4
CITY_BREAKS = ("pooled", "own")
FILES = ("departamentos", "ciudades", "nacionales")


@dataclass(frozen=True)
class LaborBaseSplice:
    """Configuration of the labor base splice.

    Attributes
    ----------
    enabled : bool
        Apply the splice. Off by default so the refactor stays equivalent.
    break_month : str
        First month of the anchored regime (``YYYY-MM``).
    window_months : int
        Months on each side of the break used to estimate it.
    city_break : str
        ``pooled`` (one common break for all cities) or ``own``.
    """

    enabled: bool = False
    break_month: str = "2001-01"
    window_months: int = 24
    city_break: str = "pooled"

    def __post_init__(self) -> None:
        RegimeSplice(break_month=self.break_month, window_months=self.window_months)  # validates both
        if self.city_break not in CITY_BREAKS:
            raise ValueError(f"city_break must be one of {CITY_BREAKS}")

    @classmethod
    def from_toml(cls, path: Path) -> LaborBaseSplice:
        """Load the configuration; a missing file means the splice is off."""
        path = Path(path)
        if not path.is_file():
            return cls()
        section = tomllib.loads(path.read_text(encoding="utf-8")).get("labor_base_splice", {})
        unknown = set(section) - {"enabled", "break_month", "window_months", "city_break"}
        if unknown:
            raise ValueError(f"Unknown labor_base_splice keys: {sorted(unknown)}")
        return cls(**section)


def _share(frame: pd.DataFrame) -> pd.Series:
    return frame["working_age"] / frame["population"]


def _breaks(frame: pd.DataFrame, key: str, config: LaborBaseSplice) -> dict[str, object]:
    """Break of the PET share of every series of ``frame``, by ``key``."""
    out = {}
    for code, group in frame.groupby(key, sort=True):
        series = _share(group.set_index("period")).sort_index()
        out[str(code)] = estimate_break(series, config.break_month, config.window_months)
    return out


def _factors(frame: pd.DataFrame, deltas: pd.Series, cut: str) -> pd.Series:
    """Per-row scale ``(share + delta) / share`` before the break, 1 from it on."""
    share = _share(frame)
    shifted = share + deltas
    before = frame["period"] < cut
    if not shifted[before].between(0, 1, inclusive="right").all():
        raise ValueError("The splice would push the working-age share outside (0, 1]")
    return pd.Series(np.where(before, shifted / share, 1.0), index=frame.index)


def _scale(frame: pd.DataFrame, factor: pd.Series) -> pd.DataFrame:
    out = frame.copy()
    for column in (*LEVELS, *(c for c in REPRESENTED if c in frame.columns)):
        out[column] = out[column] * factor
    return out


def _require(frame: pd.DataFrame, what: str) -> None:
    missing = {"period", "population", *LEVELS} - set(frame.columns)
    if missing:
        raise ValueError(f"{what} lacks columns {sorted(missing)}")


def splice_frames(
    departments: pd.DataFrame,
    cities: pd.DataFrame,
    national: pd.DataFrame,
    config: LaborBaseSplice,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Splice the PET share of the three numeric labor tables.

    Parameters
    ----------
    departments, cities, national : pandas.DataFrame
        The labor products with numeric levels. ``national`` has a
        ``national_type`` column (``ICML_COMPLETO`` and ``DANE_REFERENCIA``).
    config : LaborBaseSplice
        The enabled configuration.

    Returns
    -------
    tuple
        ``(departments, cities, national, report)``; the inputs are not
        modified and rows from the break month on are returned unchanged.
    """
    if not config.enabled:
        raise ValueError("splice_frames called with the splice disabled")
    cut = config.break_month
    for frame, what in ((departments, "departments"), (cities, "cities"), (national, "national")):
        _require(frame, what)

    department_breaks = _breaks(departments, "dep_code", config)
    delta = departments["dep_code"].astype(str).map({c: b.delta for c, b in department_breaks.items()})
    dep_factor = _factors(departments, delta, cut)
    new_departments = _scale(departments, dep_factor)

    city_breaks = _breaks(cities, "city_code", config)
    pooled = float(np.median([b.delta for b in city_breaks.values()]))
    city_delta = (
        pd.Series(pooled, index=cities.index)
        if config.city_break == "pooled"
        else cities["city_code"].astype(str).map({c: b.delta for c, b in city_breaks.items()})
    )
    city_factor = _factors(cities, city_delta, cut)
    new_cities = _scale(cities, city_factor)

    new_national = national.copy()
    reference = national["national_type"].eq("DANE_REFERENCIA")
    reference_series = _share(national[reference].set_index("period")).sort_index()
    reference_break = estimate_break(reference_series, cut, config.window_months)
    reference_rows = national[reference]
    ref_factor = _factors(reference_rows, pd.Series(reference_break.delta, index=reference_rows.index), cut)
    new_national.loc[reference] = _scale(reference_rows, ref_factor)

    # National ICML is the sum of the corrected departments before the break.
    sums = new_departments.groupby("period")[list(LEVELS)].sum()
    population = departments.groupby("period")["population"].sum()
    icml = national["national_type"].eq("ICML_COMPLETO") & (national["period"] < cut)
    if not np.allclose(population.reindex(national.loc[icml, "period"]).to_numpy(),
                       national.loc[icml, "population"].to_numpy(), rtol=0, atol=1e-3):
        raise ValueError("The departments do not add up to the national population")
    for level in LEVELS:
        new_national.loc[icml, level] = sums[level].reindex(national.loc[icml, "period"]).to_numpy()
    # Its rates are implied by those levels; the columns follow them exactly.
    for column, (top, bottom) in RATE_COLUMNS.items():
        if column in new_national.columns:
            new_national.loc[icml, column] = new_national.loc[icml, top] / new_national.loc[icml, bottom]

    strict_before = _rates(departments, cities, national[reference])
    strict_after = _rates(new_departments, new_cities, new_national[reference])
    drift = max(float((strict_after[k] - strict_before[k]).abs().max()) for k in strict_before)
    if drift > 1e-9:
        raise ValueError(f"The splice changed a labor rate by {drift:.2e}")
    icml_all = national["national_type"].eq("ICML_COMPLETO")
    icml_drift = max(
        float((new_national.loc[icml_all, top] / new_national.loc[icml_all, bottom]
               - national.loc[icml_all, top] / national.loc[icml_all, bottom]).abs().max())
        for top, bottom in RATES
    )
    if icml_drift > NATIONAL_RATE_TOLERANCE:
        raise ValueError(f"The national ICML rates moved by {icml_drift:.2e}, more than the sum of departments allows")

    before = departments["period"] < cut
    report = {
        "break_month": cut,
        "window_months": config.window_months,
        "method": "PET share splice (regression discontinuity, common slope); levels rebuilt from unchanged rates",
        "months_shifted": int(before.sum() // departments["dep_code"].nunique()),
        "rates_max_change": drift,
        "national_icml_rates_max_change": icml_drift,
        "departments": {c: {"delta_pp": 100 * b.delta, "se_pp": 100 * b.std_error_autocorrelation_adjusted}
                        for c, b in department_breaks.items()},
        "national_reference": {"delta_pp": 100 * reference_break.delta,
                               "se_pp": 100 * reference_break.std_error_autocorrelation_adjusted},
        "cities": {"mode": config.city_break, "pooled_delta_pp": 100 * pooled,
                   "own_delta_pp": {c: 100 * b.delta for c, b in city_breaks.items()}},
        "scale_factor": {"departments": [float(dep_factor[before].min()), float(dep_factor[before].max())],
                         "cities": [float(city_factor[cities["period"] < cut].min()),
                                    float(city_factor[cities["period"] < cut].max())]},
    }
    return new_departments, new_cities, new_national, report


def _rates(departments: pd.DataFrame, cities: pd.DataFrame, reference: pd.DataFrame) -> dict[str, pd.Series]:
    out = {}
    for name, frame in (("departments", departments), ("cities", cities), ("reference", reference)):
        for top, bottom in RATES:
            out[f"{name}.{top}/{bottom}"] = (frame[top] / frame[bottom]).reset_index(drop=True)
    return out


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = frame.copy()
    columns = ("population", *LEVELS, *(c for c in (*REPRESENTED, *RATE_COLUMNS) if c in frame.columns))
    for column in columns:
        numeric[column] = pd.to_numeric(frame[column], errors="raise")
    return numeric


def splice_labor_products(directory: Path, config: LaborBaseSplice) -> dict:
    """Apply the splice in place to the three labor product files.

    Only the cells that change are rewritten (every other cell keeps its exact
    text), so from the break month on the files are byte-for-byte what they
    were. A report is written beside the folder as ``labor_base_splice.json``.

    Parameters
    ----------
    directory : Path
        Folder with ``departamentos.csv``, ``ciudades.csv`` and ``nacionales.csv``.
    config : LaborBaseSplice
        The enabled configuration.
    """
    directory = Path(directory)
    text = {name: pd.read_csv(directory / f"{name}.csv", dtype=str, keep_default_na=False) for name in FILES}
    numeric = {name: _numeric(frame) for name, frame in text.items()}
    dep, cit, nat, report = splice_frames(numeric["departamentos"], numeric["ciudades"], numeric["nacionales"], config)
    for name, new in (("departamentos", dep), ("ciudades", cit), ("nacionales", nat)):
        old = numeric[name]
        for column in (*LEVELS, *(c for c in REPRESENTED if c in old.columns), *(c for c in RATE_COLUMNS if c in old.columns)):
            changed = ~np.isclose(old[column], new[column], rtol=0, atol=0)
            text[name].loc[changed, column] = [repr(float(v)) for v in new.loc[changed, column]]
        text[name].to_csv(directory / f"{name}.csv", index=False, lineterminator="\n")
    report["files"] = list(FILES)
    (directory.parent / "labor_base_splice.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report
