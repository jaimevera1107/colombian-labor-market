from pathlib import Path
import pandas as pd
import pytest

from icml.operations.informality_regeneration import _compare_h5


def _source(path: Path, perturb: float = 0, rate_perturb: float = 0):
    months = pd.period_range('2021-01','2026-08',freq='M').astype(str)
    pd.DataFrame({'period': months,
        'informal_persons_latent': [12_000_000 + perturb]*68,
        'informality_rate_latent': [.50+rate_perturb]*68,
        'reference_type':['latent_monthly_rolling3_min_second_difference']*68,
        'is_official_monthly_observation':[False]*68}).to_csv(path,index=False)


def test_h5_accepts_submilliperson_serialization_drift(tmp_path):
    one,two=tmp_path/'one.csv',tmp_path/'two.csv'
    _source(one);_source(two,perturb=.00001)
    result=_compare_h5(one,two)
    assert result['status']=='PASS'


def test_h5_rejects_rate_drift_even_when_people_similar(tmp_path):
    one,two=tmp_path/'one.csv',tmp_path/'two.csv'
    _source(one);_source(two,rate_perturb=1e-5)
    with pytest.raises(ValueError,match='informality_rate_latent'):
        _compare_h5(one,two)


def test_h5_rejects_changed_source_definition(tmp_path):
    one,two=tmp_path/'one.csv',tmp_path/'two.csv'
    _source(one);_source(two)
    df=pd.read_csv(two);df.loc[5,'reference_type']='observed_monthly';df.to_csv(two,index=False)
    with pytest.raises(ValueError,match='categorical'):
        _compare_h5(one,two)
