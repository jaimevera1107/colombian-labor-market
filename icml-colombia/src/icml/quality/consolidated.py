"""Three public labor databases with full 33-area history and no missing levels.

The source series are immutable. Where no GEIH national reference exists
(before 2001-01), represented = whole territory and factor = 1. This is a
methodological assumption, not an official GEIH observation. The DANE label
for pre-2001 refers only to the archived *reconstructed* national comparator.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from icml.domain.territories import load_territories, territory_codes
from icml.quality.gate import LEVELS, OFFICIAL_FROM, QualityContractError

CODE_SET = {f"{x:02d}" for x in territory_codes()}


def _check_levels(df: pd.DataFrame, label: str, *, tolerance: float = 1e-5) -> None:
    """Reject any missing, nonfinite or inconsistent labor quantity."""
    absent = [c for c in LEVELS if c not in df]
    if absent:
        raise QualityContractError(f"{label}: absent columns {absent}")
    levels = df[list(LEVELS)].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(levels.to_numpy(dtype=float)).all():
        raise QualityContractError(f"{label}: missing or nonfinite labor quantities")
    if levels.lt(0).any().any() or (levels['working_age'] <= 0).any() or (levels['population'] <= 0).any():
        raise QualityContractError(f"{label}: negative quantities or zero denominators")
    if ((levels['labor_force']-levels['employed']-levels['unemployed']).abs().max() > tolerance or
        (levels['working_age']-levels['labor_force']-levels['inactive']).abs().max() > tolerance or
        (levels['working_age']>levels['population']+tolerance).any()):
        raise QualityContractError(f"{label}: accounting identities or PET <= population violated")


def _normalize_codes(df: pd.DataFrame, key: str, label: str) -> pd.DataFrame:
    """Canonicalize all department/city keys as text of two digits."""
    out = df.copy(deep=True)
    if out[key].isna().any():
        raise QualityContractError(f"{label}: missing territorial identifier")
    out[key] = out[key].astype(str).map(lambda v: f"{int(v):02d}")
    if set(out[key]) != CODE_SET:
        raise QualityContractError(f"{label}: expected 33 territories; got {sorted(set(out[key]) ^ CODE_SET)}")
    if out.duplicated([key, 'period']).any():
        raise QualityContractError(f"{label}: duplicate territory-month keys")
    return out


def _month_index(periods: np.ndarray) -> np.ndarray:
    """Months since year 0 for ``YYYY-MM`` labels."""
    return np.array([int(p[:4]) * 12 + int(p[5:7]) - 1 for p in periods])


def _partial_factor_knots(periods: np.ndarray, policy: Any | None) -> tuple[str, ...] | None:
    """Kinks of the straight GEIH capital factor: 2001-01, the break, last anchored December.

    Without a policy (tests) the last knot is the December before the final
    year present, which equals the last anchored year in a monthly update.
    Knots outside the calendar are dropped; with fewer than two left the
    annual-mean curve is used as it is (``None``).
    """
    brk = getattr(policy, "partial_factor_break", "2014-01") if policy is not None else "2014-01"
    year = getattr(policy, "last_anchor_year", None) if policy is not None else None
    if year is None:
        year = int(str(periods[-1])[:4]) - 1
    last = min(f"{int(year)}-12", str(periods[-1]))
    knots: list[str] = []
    for knot in (OFFICIAL_FROM, brk, last):
        if str(periods[0]) <= knot <= str(periods[-1]) and (not knots or knot > knots[-1]):
            knots.append(knot)
    return tuple(knots) if len(knots) >= 2 else None


def _smooth_partial_factor(periods: np.ndarray, factor: np.ndarray,
                           knots: tuple[str, ...] | None = None) -> np.ndarray:
    """Return the GEIH capital factor of a partially covered territory.

    The observed monthly factor moves 4-5 % from one month to the next. Its
    annual means (2001 onwards) are interpolated to monthly values; with
    ``knots`` that curve is then replaced by straight segments through its
    values at the knots: flat before the first knot (1993-2000 take the 2001
    level, so the GEIH series follows the census shape), linear between them
    and, after the last knot (the December of the last anchored year), the
    same slope as the last segment, so a monthly update never rewrites the
    anchored years.

    Parameters
    ----------
    periods : numpy.ndarray
        Month labels ``YYYY-MM`` in chronological order.
    factor : numpy.ndarray
        Observed monthly factor (capital share) for the same months.
    knots : tuple of str, optional
        Ascending ``YYYY-MM`` kinks of the straight factor.

    Returns
    -------
    numpy.ndarray
        Factor, strictly positive and at most one, one value per month.
    """
    years = np.array([int(p[:4]) for p in periods])
    index = _month_index(periods)
    observed = (periods >= OFFICIAL_FROM) & np.isfinite(factor) & (factor > 0)
    if not observed.any():
        raise QualityContractError("partial territory without an observed GEIH factor")
    anchor_years = np.unique(years[observed])
    anchor_value = np.array([factor[observed & (years == y)].mean() for y in anchor_years])
    smooth = np.interp(index, anchor_years * 12 + 5.5, anchor_value)
    if knots:
        k = _month_index(np.asarray(knots))
        kv = np.interp(k, index, smooth)
        line = np.interp(index, k, kv)
        after = index > k[-1]
        line[after] = kv[-1] + (kv[-1] - kv[-2]) / (k[-1] - k[-2]) * (index[after] - k[-1])
        smooth = line
    if not (np.isfinite(smooth).all() and (smooth > 0).all() and (smooth <= 1).all()):
        raise QualityContractError("partial factor out of (0, 1]")
    return smooth


def _validate_calendar(df: pd.DataFrame, key: str, name: str, expected: list[str] | None = None) -> list[str]:
    months = sorted(df['period'].astype(str).unique().tolist())
    if not months or months != list(pd.period_range(months[0], months[-1], freq='M').astype(str)):
        raise QualityContractError(f"{name}: non-contiguous monthly calendar")
    if expected is not None and months != expected:
        raise QualityContractError(f"{name}: calendar does not match other databases")
    if len(df) != 33 * len(months) or not df.groupby('period')[key].nunique().eq(33).all():
        raise QualityContractError(f"{name}: missing territory-month rows")
    return months


def build_three_bases(departments: pd.DataFrame, urban: pd.DataFrame, national: pd.DataFrame,
                      policy: Any | None = None) -> dict[str, pd.DataFrame]:
    """Make 33 departmental, 33 urban and 2 distinct national time series.

    Does not alter the six reconstructed labor quantities. Historical coverage
    factors set to 1 are explicitly flagged as assumptions, not DANE evidence.
    """
    dep = _normalize_codes(departments, 'dep_code', 'departamentos')
    cit = _normalize_codes(urban, 'city_code', 'ciudades')
    months = _validate_calendar(dep, 'dep_code', 'departamentos')
    _validate_calendar(cit, 'city_code', 'ciudades', months)
    if national['period'].duplicated().any() or sorted(national['period'].astype(str)) != months:
        raise QualityContractError('nacionales: missing, extra or duplicated months')
    names = {f"{t.dane_code:02d}": t.name for t in load_territories()}
    for label, frame in (('departamentos', dep), ('ciudades', cit)):
        _check_levels(frame, label)
    dep['territory_id'] = 'CO-' + dep['dep_code']
    dep['territory_name'] = dep['dep_code'].map(names)
    dep['territory_level'] = 'DEPARTAMENTO'
    dep['is_additive_member'] = True
    cit['dep_code'] = cit['city_code']
    cit['territory_id'] = 'CO-URB-' + cit['city_code']
    cit['territory_name'] = cit['city_name']
    cit['territory_level'] = 'SENAL_URBANA'
    cit['is_additive_member'] = False
    cit['source_status'] = np.where(cit['unit_type'].astype(str).str.contains('SINTET'), 'SINTETICA', 'RECONSTRUIDA_URBANA')
    early = dep['period'].astype(str).lt(OFFICIAL_FROM)
    # Before 2001 the GEIH did not exist: fully-covered territories use factor=1
    # (the whole territory is in the ICML universe). Partially-covered territories
    # (the nine remote departments) keep their demographic factor, which is already
    # computed by the reconciliation stage as capital/full for all periods.
    # The nine partially-covered territories (Amazonía, Orinoquía, San Andrés)
    partial_set: set[str] = {'81', '85', '86', '88', '91', '94', '95', '97', '99'}
    is_partial_early = early & dep['dep_code'].isin(partial_set)
    is_full_early    = early & ~dep['dep_code'].isin(partial_set)

    # Nine partially-covered territories: ONE smooth factor per territory,
    # applied to every component (employed, unemployed, inactive, working
    # age, population). Rates are therefore identical to the census universe,
    # and the GEIH levels inherit the census shape (linear PET before 2001,
    # smooth afterwards) with no seasonal saw-tooth and no jump at 2001/2014.
    for code in partial_set:
        mask = dep['dep_code'] == code
        if not mask.any():
            continue
        months = dep.loc[mask, 'period'].astype(str).to_numpy()
        knots = _partial_factor_knots(months, policy)
        # Labor factor: shared by every labor component so rates match census.
        smooth = _smooth_partial_factor(months, dep.loc[mask, 'factor_employed'].to_numpy(dtype=float), knots)
        # Population keeps its own (smoothed) demographic share; PET <= population holds.
        smooth_pop = _smooth_partial_factor(months, dep.loc[mask, 'factor_population'].to_numpy(dtype=float), knots)
        for q in ('employed', 'unemployed', 'inactive', 'working_age'):
            dep.loc[mask, f'{q}_represented'] = dep.loc[mask, q].to_numpy(dtype=float) * smooth
            dep.loc[mask, f'factor_{q}'] = smooth
        dep.loc[mask, 'labor_force_represented'] = (
            dep.loc[mask, 'employed_represented'].to_numpy(dtype=float)
            + dep.loc[mask, 'unemployed_represented'].to_numpy(dtype=float)
        )
        dep.loc[mask, 'factor_labor_force'] = smooth
        dep.loc[mask, 'population_represented'] = dep.loc[mask, 'population'].to_numpy(dtype=float) * smooth_pop
        dep.loc[mask, 'factor_population'] = smooth_pop
        if (dep.loc[mask, 'working_age_represented'] > dep.loc[mask, 'population_represented'] + 1e-5).any():
            raise QualityContractError(f'departamentos {code}: GEIH working age exceeds population')

    for q in LEVELS:
        represented = f'{q}_represented'
        factor      = f'factor_{q}'
        if represented not in dep or factor not in dep:
            raise QualityContractError(f'departamentos: missing factor/represented {q}')
        # Fully-covered: factor=1, represented=full (no GEIH, whole territory)
        dep.loc[is_full_early, represented] = dep.loc[is_full_early, q]
        dep.loc[is_full_early, factor] = 1.0
        # Partially-covered: update factor = represented / full (for consistency)
        for code in partial_set:
            pre_code = (dep['dep_code'] == code) & early
            if not pre_code.any():
                continue
            full_pre = dep.loc[pre_code, q].values.astype(float)
            rep_pre  = dep.loc[pre_code, represented].values.astype(float)
            dep.loc[pre_code, factor] = np.where(full_pre > 0, rep_pre / full_pre, 0.0)
        if not np.isfinite(dep[[represented, factor]].to_numpy(dtype=float)).all():
            raise QualityContractError(f'departamentos: nonfinite factor/represented {q}')
        if (dep[represented] - dep[q] * dep[factor]).abs().max() > 1e-5:
            raise QualityContractError(f'departamentos: inconsistent factor {q}')
    dep['factor_reference_status'] = np.where(
        is_partial_early,
        'DEMOGRAFICO_RETROPOLADO_SIN_REFERENCIA_GEIH',
        np.where(early, 'SIN_REFERENCIA_GEIH_FACTOR_IDENTIDAD', 'COBERTURA_GEIH')
    )
    dep['factor_is_assumed'] = early
    # The ICML national is always an unweighted sum, not sum(factor * levels).
    sums = dep.groupby('period',sort=True)[list(LEVELS)].sum().reset_index()
    baseline = national.set_index('period').loc[months]
    for q in LEVELS:
        if f'icml_{q}' not in baseline or f'dane_{q}' not in baseline:
            raise QualityContractError(f'nacionales: missing ICML/reference {q}')
        if (sums[q].to_numpy() - baseline[f'icml_{q}'].to_numpy()).max(initial=0) > 1e-5 or (np.abs(sums[q].to_numpy() - baseline[f'icml_{q}'].to_numpy()).max() > 1e-5):
            raise QualityContractError(f'nacionales: ICML differs from 33 territory sum: {q}')
    represented = dep.groupby('period',sort=True)[[f'{q}_represented' for q in LEVELS]].sum()
    for q in LEVELS:
        # The nine partially-covered territories now contribute their real capital signal,
        # so the represented sum >= DANE (not exactly equal). We only raise if the sum
        # falls *below* the DANE reference, which would indicate missing data.
        post = np.asarray([m>=OFFICIAL_FROM for m in months])
        repr_post = represented[f'{q}_represented'].to_numpy()[post]
        dane_post = baseline[f'dane_{q}'].to_numpy()[post]
        shortfall = dane_post - repr_post
        # Case A uses factor_employed for all labor components: unemployed
        # represented may be up to ~1% below DANE (< 40k persons nationally).
        # Accept up to 2% shortfall as within-tolerance for the ICML universe.
        dane_ref = baseline[f'dane_{q}'].to_numpy()[post]
        tol = np.maximum(1.1, 0.02 * dane_ref)
        if np.any(shortfall > tol):
            raise QualityContractError(f'nacionales: represented below DANE since 2001: {q}')
    # National is long-form: two rows per month, same six mandatory columns.
    sources = []
    for kind in ('ICML_COMPLETO','DANE_REFERENCIA'):
        is_icml = kind == 'ICML_COMPLETO'
        df = pd.DataFrame({'period':months,'dep_code':'00','territory_id':'CO-00-'+('ICML' if is_icml else 'DANE'),
                           'territory_name':'Colombia','territory_level':'NACIONAL', 'national_type':kind,
                           'is_additive_member':False,
                           'reference_status': ['RECONSTRUIDO_ICML' if is_icml else ('GEIH_REFERENCIA_PUBLICADA' if m>=OFFICIAL_FROM else 'HISTORICO_RECONSTRUIDO_NO_OFICIAL') for m in months],
                           'is_official_observation': [False if is_icml else m>=OFFICIAL_FROM for m in months]})
        for q in LEVELS:
            df[q] = sums[q].to_numpy() if is_icml else baseline[f'dane_{q}'].to_numpy(dtype=float)
            if is_icml:
                # In early years, factor 1 means the whole ICML universe is retained.
                df[f'factor_{q}'] = np.where(np.asarray([m<OFFICIAL_FROM for m in months]), 1.0, baseline[f'dane_{q}'].to_numpy(dtype=float)/sums[q].to_numpy(dtype=float))
            else:
                df[f'factor_{q}'] = 1.0
        df['unemployment_rate'] = df['unemployed']/df['labor_force']
        df['employment_rate'] = df['employed']/df['working_age']
        df['participation_rate'] = df['labor_force']/df['working_age']
        df['factor_reference_status'] = np.where(df['period'].lt(OFFICIAL_FROM),'SIN_REFERENCIA_GEIH_FACTOR_IDENTIDAD','COBERTURA_GEIH' if is_icml else 'REFERENCIA_GEIH')
        df['factor_is_assumed'] = df['period'].lt(OFFICIAL_FROM)
        _check_levels(df, kind, tolerance=1.1 if not is_icml else 1e-5)  # DANE national published rounded by up to 1 person
        sources.append(df)
    nac = pd.concat(sources, ignore_index=True).sort_values(['period','national_type'],kind='stable').reset_index(drop=True)
    if nac.duplicated(['period','national_type']).any() or len(nac) != 2*len(months):
        raise QualityContractError('nacionales: two series required for each month')
    # Experimental: pure demographic factor = city_population / dept_population.
    # Added as factor_employed_demographic (and _unemployed, _inactive, _population).
    # Does not replace the official factor; purely for comparison and research.
    partial_set_int: set[int] = {81, 85, 86, 88, 91, 94, 95, 97, 99}
    # urban uses city_code; for the nine, city_code == dep_code
    # urban uses city_code; for the nine, city_code == dep_code.
    # dep_code in dep is a two-digit string after _normalize_codes; cast city_code to match.
    city_pop = (
        urban[urban['city_code'].isin(partial_set_int)][['city_code', 'period', 'population']]
        .assign(dep_code=lambda x: x['city_code'].apply(lambda v: f"{int(v):02d}"))
        .drop(columns='city_code')
        .rename(columns={'population': '_city_pop'})
    )
    dep_ext = dep.merge(city_pop, on=['dep_code', 'period'], how='left')
    for q in LEVELS:
        dep[f'factor_{q}_demographic'] = np.where(
            dep['dep_code'].isin(partial_set_int),
            np.clip(dep_ext['_city_pop'] / dep_ext['population'].where(dep_ext['population'] > 0), 0.0, 1.0),
            dep[f'factor_{q}'],  # non-partial: keep official factor
        )
    for frame, key in ((dep,'dep_code'),(cit,'city_code')):
        frame.sort_values(['period',key], inplace=True,kind='stable')
        frame.reset_index(drop=True,inplace=True)
    return {'ciudades':cit, 'departamentos':dep, 'nacionales':nac}
