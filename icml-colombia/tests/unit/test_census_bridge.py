"""Reversible census bridge independent of labor model dependencies."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from icml.census_bridge import BASE, NINE, build


@pytest.fixture(scope="module")
def frames():
    periods = pd.period_range("1993-01", "2026-08", freq="M").astype(str)
    rows=[]; urb=[]
    for p in periods:
        for code in range(1,34):
            # Remap nine synthetic identifiers to real DIVIPOLA codes
            dep = NINE[code-25] if code>=25 else code
            full={"employed":4000.0,"unemployed":500.0,"inactive":1500.0,
                  "labor_force":4500.0,"working_age":6000.0,"population":10000.0}
            covered={q:v*0.3 for q,v in full.items()}
            ratio=(1.0 if p<"2001-01" else (0 if p<"2014-01" else .3)) if dep in NINE else 1.0
            rows.append({"period":p,"dep_code":dep,**full,
                         **{f"{q}_represented":v*ratio for q,v in full.items()}})
            urb.append({"period":p,"dep_code":dep,**covered})
    dept=pd.DataFrame(rows); cities=pd.DataFrame(urb)
    group=dept.groupby("period",as_index=False).sum(numeric_only=True)
    nations=pd.concat([pd.DataFrame({"period":group.period,"national_type":typ,
        **{q:group[q] if typ=="ICML_COMPLETO" else group[f"{q}_represented"] for q in BASE}})
        for typ in ("ICML_COMPLETO","DANE_REFERENCIA")],ignore_index=True)
    census=pd.DataFrame({"dep_code":NINE,"cnpv_departamento_ajustado":10000.0,
                         "cnpv_cabecera_capital":2800.0})
    return dept,cities,nations,census


def test_anchoring_and_roundtrip(frames):
    anchors, d, national, metrics, gates, summary=build(*frames)
    assert len(d)==13332
    assert summary["months"]==404
    for dep in NINE:
        subset=d[(d.dep_code==dep)&d.period.str.startswith("2018-")]
        assert np.isclose(subset.geih_population.mean(),2800)
    for q in BASE:
        assert np.allclose(d[q],d[f"geih_{q}"]+d[f"outside_geih_{q}"],atol=1e-6)
        assert d[f"factor_geih_{q}"].between(0,1).all()
    assert gates[gates.gate=="cnpv_2018_cabecera_representado"].passed.iloc[0]


def test_early_exclusion_and_historical_proxy(frames):
    _,d,_,_,_,_=build(*frames)
    special=d[d.dep_code.isin(NINE)]
    assert (special[special.period.between("2001-01","2013-12")].geih_population==0).all()
    assert (special[special.period.lt("2001-01")].geih_population>0).all()
    assert (special[special.period.ge("2014-01")].geih_population>0).all()


def test_unanchored_full_levels_unchanged(frames):
    dept=frames[0]
    _,d,_,_,_,_=build(*frames)
    base=dept.sort_values(["period","dep_code"]).reset_index(drop=True)
    for q in BASE:
        assert np.array_equal(base[q].to_numpy(),d[q].to_numpy())


def test_census_validation(frames):
    bad=frames[3].iloc[:-1]
    with pytest.raises(ValueError,match="exactly nine"):
        build(frames[0],frames[1],frames[2],bad)
