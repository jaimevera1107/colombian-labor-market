"""Contract tests for read-only postclosure audit (no departmental truths)."""

import numpy as np
import pandas as pd
import pytest

from icml.informality.national_closure import calibrate_month
from icml.informality import postclosure_evaluation as postclosure
from icml.informality.postclosure_evaluation import _validate


def test_second_national_margin_is_not_neutral_to_relative_ranking():
    # Both constraints close, even though rankings may change with f.
    employed = np.ones(33)*1000.
    rates = np.linspace(.40, .60, 33)
    factor = np.linspace(0.2, 1., 33)
    a = calibrate_month(rates, employed, factor, 17000., 11100.)
    assert abs(np.dot(employed, a["calibrated_rate"])-17000.) < 1e-4
    assert abs(np.dot(employed*factor, a["calibrated_rate"])-11100.) < 1e-4
    assert (a["calibrated_rate"]>=0).all()
    assert (a["calibrated_rate"]<=1).all()


def test_postclosure_rejects_wrong_frozen_employment(monkeypatch):
    monkeypatch.setattr(postclosure, "PERIODS", pd.period_range("2001-01", periods=1, freq="M"))
    departments=np.arange(1,34)
    d=pd.DataFrame({"dep_code":departments,"period":"2001-01", "employed":100.,
                    "factor_employed":1.0,"rate_prior":.4,"rate_calibrated":.4,
                    "informal":40.,"formal":60.,"informal_represented":40.,
                    "formal_represented":60.})
    l=d[["dep_code","period","employed","factor_employed"]].copy()
    l.loc[0,"employed"]=110.
    n=pd.DataFrame({"period":["2001-01","2001-01"],
                    "national_type":["ICML_COMPLETO","DANE_REFERENCIA"],
                    "informal_estimated":[1320.,1320.]})
    with pytest.raises(ValueError,match="frozen employed altered"):
        _validate(d,l,n,"urban_direct")


def test_postclosure_rejects_missing_territories():
    d=pd.DataFrame({"dep_code":[1],"period":["1993-01"], "employed":[100.],
                    "factor_employed":[1.],"rate_prior":[.4],"rate_calibrated":[.4],
                    "informal":[40.],"formal":[60.],"informal_represented":[40.],
                    "formal_represented":[60.]})
    l=d[["dep_code","period","employed","factor_employed"]]
    n=pd.DataFrame({"period":["1993-01"],"national_type":["ICML_COMPLETO"],
                    "informal_estimated":[40.]})
    with pytest.raises(ValueError,match="unexpected missing / extra periods"):
        _validate(d,l,n,"urban_direct")
