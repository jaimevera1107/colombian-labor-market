"""Coverage and identity rules for the final three-file labor delivery."""
import numpy as np
import pandas as pd
import pytest

from icml.domain.territories import territory_codes
from icml.quality.consolidated import build_three_bases
from icml.quality.gate import QualityContractError, LEVELS


def example():
    periods = ['2000-12', '2001-01', '2001-02']
    rows = []
    for p in periods:
        for code in territory_codes():
            values = dict(employed=90.0, unemployed=10.0, inactive=50.0,
                          labor_force=100.0, working_age=150.0, population=250.0)
            row = dict(period=p, dep_code=code, source='TEST', **values)
            for q in LEVELS:
                row[f'{q}_represented'] = values[q] if code != 81 or p >= '2001-01' else 0.0
                row[f'factor_{q}'] = 1.0 if code != 81 or p >= '2001-01' else 0.0
            rows.append(row)
    deps = pd.DataFrame(rows)
    cities = deps[['period','dep_code',*LEVELS]].rename(columns={'dep_code':'city_code'}).copy()
    cities['city_name'] = 'City'
    cities['unit_type'] = 'CIUDAD_O_AREA_METROPOLITANA'
    national = []
    for p in periods:
        entry={'period':p}
        for q in LEVELS:
            entry[f'icml_{q}']=33*float(deps.iloc[0][q])
            entry[f'dane_{q}']=33*float(deps.iloc[0][q]) if p > '2000-12' else 31*float(deps.iloc[0][q])
        national.append(entry)
    return deps,cities,pd.DataFrame(national)


def test_three_products_coverage_and_full_early_history():
    deps,cities,national=example()
    result=build_three_bases(deps,cities,national)
    assert set(result)=={'ciudades','departamentos','nacionales'}
    assert len(result['departamentos'])==99
    assert len(result['ciudades'])==99
    assert len(result['nacionales'])==6
    for f in result.values():
        assert f[list(LEVELS)].notna().all().all()
    post=result['departamentos']
    assert post.loc[post.period=='2000-12',[f'factor_{q}' for q in LEVELS]].eq(1).all().all()
    assert post.loc[(post.period=='2000-12')&(post.dep_code=='81'),'employed_represented'].iloc[0]==90
    assert deps.loc[(deps.period=='2000-12')&(deps.dep_code==81),'employed_represented'].iloc[0]==0
    assert result['nacionales'].loc[result['nacionales'].national_type=='ICML_COMPLETO','employed'].eq(2970).all()
    assert result['nacionales'].loc[(result['nacionales'].period=='2000-12')&(result['nacionales'].national_type=='DANE_REFERENCIA'),'is_official_observation'].iloc[0]==False
    assert not result['departamentos'].dep_code.eq('00').any()


def test_missing_labor_quantity_hard_error():
    deps,cities,national=example()
    cities.loc[0,'employed']=np.nan
    with pytest.raises(QualityContractError,match='missing or nonfinite'):
        build_three_bases(deps,cities,national)


def test_missing_territory_month_hard_error():
    deps,cities,national=example()
    with pytest.raises(QualityContractError,match='missing territory-month'):
        build_three_bases(deps.iloc[1:],cities,national)


def test_wrong_national_sum_hard_error():
    deps,cities,national=example()
    national.loc[0,'icml_employed']+=1
    with pytest.raises(QualityContractError,match='ICML differs'):
        build_three_bases(deps,cities,national)


def test_corrupted_official_weighted_sum_hard_error():
    deps,cities,national=example()
    # Corrupt anchored territories (the nine partial ones are rebuilt from one
    # smooth factor, so a corruption there is overwritten by construction).
    rows=(deps.period=='2001-02')&deps.dep_code.isin([5,8,11,13,15,17])
    deps.loc[rows,'factor_employed']=0.5
    deps.loc[rows,'employed_represented']=deps.loc[rows,'employed']*0.5
    with pytest.raises(QualityContractError,match='represented below DANE'):
        build_three_bases(deps,cities,national)
