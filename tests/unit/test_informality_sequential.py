"""Regression guards for the sequential informal-employment methodology."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from icml.informality.sequential import (
    _bridge_10_city, _check_rates, build_national, run,
)


def test_backward_bridge_preserves_constant_national_shape():
    n=np.full(404,.53)
    u=np.full(404,.12)
    result=_bridge_10_city(np.zeros(404),n,u,u,.42,168)
    assert result.shape==(168,)
    assert np.max(abs(result-.42))<1e-12


def test_backward_bridge_responds_to_national_history():
    n=np.linspace(.62,.45,404)
    u=np.full(404,.12)
    out=_bridge_10_city(np.zeros(404),n,u,u,.40,168)
    assert out[0]>.40
    assert abs(out[-1]-.40)<.001


def test_rates_must_be_bounded_and_complete():
    for x in (np.array([.1,np.nan]),np.array([.2,1.1]),np.array([-.1,.5])):
        with pytest.raises(ValueError,match='Invalid rates'):
            _check_rates(x,'synthetic')


def test_national_cannot_run_before_thirteen_city_stage():
    bad=pd.DataFrame({'city_code':[5],'period':['1993-01']})
    with pytest.raises(ValueError,match='Stage 13 absent'):
        build_national(bad,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame())


def test_existing_experiment_directory_cannot_be_overwritten(tmp_path):
    out=tmp_path/'already';out.mkdir();(out/'manifest.json').write_text('existing')
    with pytest.raises(FileExistsError):
        run(tmp_path/'not_a_file_1',tmp_path/'not_a_file_2',
            tmp_path/'not_a_file_3',tmp_path/'not_a_file_4',
            tmp_path/'not_a_file_5',tmp_path/'not_a_file_6',out)


def test_calibration_uses_two_denominators_without_changing_employment():
    from icml.informality.sequential import diagnostic_dual_calibration
    codes=[5,8,11,13]
    b=pd.DataFrame({'period':['2010-01']*4,'dep_code':codes,
                    'urban_transfer_baseline_rate':[.2,.3,.4,.2]})
    d=pd.DataFrame({'period':['2010-01']*4,'dep_code':codes,
                    'employed':[100.]*4,'factor_employed':[1.,1.,0.,0.]})
    n=pd.DataFrame({'period':['2010-01']*2,
             'national_type':['ICML_COMPLETO','DANE_REFERENCIA'],
             'employed_frozen':[400.,200.],
             'informality_rate_estimated':[.5,.6]})
    post,diag=diagnostic_dual_calibration(b,d,n)
    assert np.allclose(post.employed,100)
    assert abs(np.dot(post.informal_diagnostic,post.factor_employed)/200-.6)<1e-10
    assert abs(post.informal_diagnostic.sum()/400-.5)<1e-10
    assert (post.informal_diagnostic+post.formal_diagnostic-post.employed).abs().max()<1e-10
    assert diag.dane_reference_comparable.iloc[0]


def test_pre2001_uses_full_reconstructed_icml_not_false_official_reference():
    from icml.informality.sequential import diagnostic_dual_calibration
    codes=[5,8]
    b=pd.DataFrame({'period':['1998-01']*2,'dep_code':codes,
                    'urban_transfer_baseline_rate':[.25,.35]})
    d=pd.DataFrame({'period':['1998-01']*2,'dep_code':codes,
                    'employed':[100.,150.],'factor_employed':[1.,1.]})
    n=pd.DataFrame({'period':['1998-01']*2,
            'national_type':['ICML_COMPLETO','DANE_REFERENCIA'],
            'employed_frozen':[250.,300.],
            'informality_rate_estimated':[.5,.4]})
    post,diag=diagnostic_dual_calibration(b,d,n)
    assert abs(post.informal_diagnostic.sum()/250-.5)<1e-10
    assert not diag.dane_reference_comparable.iloc[0]
    assert np.isnan(diag.post_repr_residual_pp.iloc[0])
