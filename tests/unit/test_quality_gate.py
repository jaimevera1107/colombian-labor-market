"""No goldens required: final-gate accounting and adverse examples."""

import numpy as np
import pandas as pd
import pytest

from icml.domain.territories import territory_codes
from icml.quality.gate import (
    QualityContractError,
    QualityPolicy,
    audit_products,
    extreme_changes,
    structural_breaks,
    annual_linearity,
    unify_territories,
)

Q = ("employed", "unemployed", "inactive", "labor_force", "working_age", "population")


def fixtures():
    months = pd.period_range("2000-11", "2002-12", freq="M").astype(str)
    rows = []
    for p in months:
        for code in territory_codes():
            row = {"period": p, "dep_code": code, "source": "PRUEBA"}
            row.update({"employed": 90., "unemployed": 10., "inactive": 50., "labor_force": 100., "working_age": 150., "population": 250.})
            for q in Q:
                row[f"{q}_represented"] = row[q]
                row[f"factor_{q}"] = 1.
            row.update({"year": int(p[:4]), "unemployment_rate": .1,
                        "employment_rate": .6, "participation_rate": 2/3})
            rows.append(row)
    deps = pd.DataFrame(rows)
    nat = []
    for p in months:
        values = {"period":p}
        for q in Q:
            values[f"icml_{q}"] = float(deps[deps.period==p][q].sum())
            values[f"dane_{q}"] = values[f"icml_{q}"]
        nat.append(values)
    return deps, pd.DataFrame(nat)


def test_unifies_one_national_per_month_and_preserves_deps():
    deps, nat = fixtures()
    unified = unify_territories(deps,nat)
    assert unified.groupby("period").size().eq(34).all()
    assert unified.dep_code.eq("00").sum() == 26
    assert unified[unified.dep_code=='00'].is_additive_member.eq(False).all()
    assert unified[unified.dep_code!='00'].is_additive_member.all()
    assert (unified.territory_id == 'CO-' + unified.dep_code).all()
    for q in Q:
        np.testing.assert_allclose(unified.loc[unified.dep_code=='00',q],nat[f'icml_{q}'])
        assert unified[unified.period<'2001-01'].loc[lambda x:x.dep_code=='00',f'factor_{q}'].eq(1).all()
        assert unified[unified.period>='2001-01'].loc[lambda x:x.dep_code=='00',f'factor_{q}'].eq(1).all()
    assert np.allclose(
        unified[unified.dep_code!='00'].employed.to_numpy(),
        deps.sort_values(['period','dep_code']).employed.to_numpy()
    )


def test_duplicate_keys_rejected():
    deps,nat = fixtures()
    with pytest.raises(QualityContractError,match='duplicated'):
        unify_territories(pd.concat([deps,deps.iloc[:1]]),nat)


def test_extreme_change_growth_fall_and_zero():
    periods = pd.period_range('2020-01',periods=4,freq='M').astype(str)
    frame=pd.DataFrame({"city_code":[91]*4,"period": periods,
                        "employed":[1.,3.1,1.,0.],"unemployed":[1.,1.,1.,1.],
                        "inactive":[1.]*4,"working_age":[4.]*4,"population":[5.]*4})
    diag=extreme_changes(frame,'city_code',QualityPolicy(),'CITY')
    assert len(diag)==3
    assert (diag.rule=='SYMMETRIC_200_PCT').sum()==2
    assert (diag.rule=='ZERO_TRANSITION').sum()==1
    assert diag.loc[diag.rule=='ZERO_TRANSITION','change_pct'].iloc[0] == -100


def test_structural_shift_is_screen_not_failure():
    months=pd.period_range('2020-01',periods=40,freq='M').astype(str)
    rate=np.array([.1]*20+[.22]*20)
    df=pd.DataFrame({'dep_code':['05']*40,'period':months,'unemployment_rate':rate,
                     'employment_rate':.5,'participation_rate':.6})
    s=structural_breaks(df,'dep_code',QualityPolicy(),'TEST')
    assert (s.rate=='unemployment_rate').any()
    assert s.shift_pp.abs().max() >= 10


def test_audit_fails_wrong_represented_reference_but_does_not_mutate():
    deps,nat=fixtures()
    unified=unify_territories(deps,nat)
    urban=(deps.rename(columns={'dep_code':'city_code'}).copy())
    # no need actual observed cities; this tests accounting in the synthetic panel
    x=unified.copy(deep=True)
    u=urban.copy(deep=True)
    diag,summary=audit_products(x,u,nat)
    assert summary['status']=='REQUIRES_METHODOLOGICAL_REVIEW'
    assert summary['hard_failures']==[]
    x.loc[(x.dep_code=='05') & (x.period=='2001-01'),'employed_represented']+=50
    _,bad=audit_products(x,u,nat)
    assert bad['status']=='BLOCKED'
    assert any('represented' in msg for msg in bad['hard_failures'])
    assert (unified.employed_represented==unify_territories(deps,nat).employed_represented).all()


def test_annual_linearity_flags_population_plateau_and_pet_wiggles():
    months = pd.period_range("2020-01", periods=12, freq="M").astype(str)
    df=pd.DataFrame({"dep_code":[27]*12,"period":months,
                     "population":[500000.0]*12,
                     "working_age":[300000.,300200.,300100.,340000.]+[300000.]*8})
    rows=annual_linearity(df,"dep_code","DEPARTAMENTO")
    assert rows.loc[rows.quantity=="population","annual_plateau"].iloc[0]
    assert rows.loc[rows.quantity=="working_age","shape_flag"].iloc[0]=="STRONG_NONLINEARITY"
