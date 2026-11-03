"""Three public labor databases with full 33-area history and no missing levels.

The source series are immutable. Where no GEIH national reference exists
(before 2001-01), represented = whole territory and factor = 1. This is a
methodological assumption, not an official GEIH observation. The DANE label
for pre-2001 refers only to the archived *reconstructed* national comparator.
"""
from __future__ import annotations

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


def _validate_calendar(df: pd.DataFrame, key: str, name: str, expected: list[str] | None = None) -> list[str]:
    months = sorted(df['period'].astype(str).unique().tolist())
    if not months or months != list(pd.period_range(months[0], months[-1], freq='M').astype(str)):
        raise QualityContractError(f"{name}: non-contiguous monthly calendar")
    if expected is not None and months != expected:
        raise QualityContractError(f"{name}: calendar does not match other databases")
    if len(df) != 33 * len(months) or not df.groupby('period')[key].nunique().eq(33).all():
        raise QualityContractError(f"{name}: missing territory-month rows")
    return months


def build_three_bases(departments: pd.DataFrame, urban: pd.DataFrame, national: pd.DataFrame) -> dict[str, pd.DataFrame]:
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
    # Only correct reference representation. Actual reconstructed levels remain unchanged.
    for q in LEVELS:
        represented = f'{q}_represented'
        factor = f'factor_{q}'
        if represented not in dep or factor not in dep:
            raise QualityContractError(f'departamentos: missing factor/represented {q}')
        dep.loc[early, represented] = dep.loc[early, q]
        dep.loc[early, factor] = 1.0
        if not np.isfinite(dep[[represented, factor]].to_numpy(dtype=float)).all():
            raise QualityContractError(f'departamentos: nonfinite factor/represented {q}')
        if (dep[represented] - dep[q] * dep[factor]).abs().max() > 1e-5:
            raise QualityContractError(f'departamentos: inconsistent factor {q}')
    dep['factor_reference_status'] = np.where(early, 'SIN_REFERENCIA_GEIH_FACTOR_IDENTIDAD', 'COBERTURA_GEIH')
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
        # No GEIH monthly coverage requirement before 2001; enforce it after 2001.
        post = np.asarray([m>=OFFICIAL_FROM for m in months])
        if np.max(np.abs(represented[f'{q}_represented'].to_numpy()[post] - baseline[f'dane_{q}'].to_numpy()[post]), initial=0)>1.1:
            raise QualityContractError(f'nacionales: represented not equal DANE since 2001: {q}')
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
    for frame, key in ((dep,'dep_code'),(cit,'city_code')):
        frame.sort_values(['period',key], inplace=True,kind='stable')
        frame.reset_index(drop=True,inplace=True)
    return {'ciudades':cit, 'departamentos':dep, 'nacionales':nac}
