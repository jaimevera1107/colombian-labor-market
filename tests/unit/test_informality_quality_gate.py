"""Tests contractuales de auditoría 13→nacional→23→predicción."""
import numpy as np
import pandas as pd

from icml.informality.quality_gate import _complete, _counts_check, _temporal


def test_coverage_rejects_missing_month_even_when_lengths_might_match():
    cal=pd.period_range('1993-01','2026-08',freq='M').astype(str)
    df=pd.DataFrame({'city_code':[1]*len(cal), 'period':cal})
    assert _complete(df,'city_code',1)==(True,0)
    df.loc[0,'period']='2026-08'
    passed,errors=_complete(df,'city_code',1)
    assert not passed and errors>0


def test_accounts_detect_frozen_denominator_mutation():
    frame=pd.DataFrame({'period':['2025-01'],'city_code':[5], 'employed_frozen':[100.],
                        'informal_estimated':[41.],'formal_estimated':[59.]})
    lab=pd.DataFrame({'period':['2025-01'],'city_code':[5],'employed':[100.]})
    assert _counts_check(frame,lab,['period','city_code'],'city_code')['passed']
    lab.employed=101.
    assert not _counts_check(frame,lab,['period','city_code'],'city_code')['passed']


def test_extreme_threshold_is_symmetric_and_non_destructive():
    months=pd.period_range('1993-01',periods=28,freq='M').astype(str)
    rates=[.2]*12+[.8]*12+[.2]*4
    data=pd.DataFrame({'city_code':[5]*28,'period':months,'informality_rate':rates,
                       'informal_estimated':np.array(rates)*1000.})
    alert,breaks=_temporal(data,'city_code','informality_rate',level='city')
    assert (alert.greater_than_200pct_equiv).any()
    assert len(breaks)>0
    assert all(alert.decision=='REVIEW_NOT_AUTO_CORRECT')
