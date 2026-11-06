"""DANE urban-first historical backcast: mathematical and contract tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from icml.informality.urban_backcast import (
    ALIAS, FIRST_13, _normal, _solve_rolling_rates, _city_windows, NEW,
)


def test_aliases_and_13_reference_set():
    assert len(FIRST_13)==13
    assert ALIAS[_normal('Bogotá D.C.')]==ALIAS[_normal('Bogotá')]==11
    assert ALIAS[_normal('Montería')]==ALIAS[_normal('Monteria')]==23
    assert 25 not in FIRST_13


def test_old_rolling_source_smooth_and_bounded():
    cal=pd.date_range('2019-01-01',periods=9,freq='MS')
    src=pd.DataFrame({'period_start':cal[:7], 'period_end':cal[2:],
        'informality_rate':[.5]*7,'occupied_thousands':[10]*7,
        'informal_thousands':[5]*7,'eligible_for_training':[True]*7,
        'concept':['Test']*7,'definition':['old_small_firm_size']*7})
    sol,audit=_solve_rolling_rates(src,cal)
    assert len(sol)==9 and abs(sol.mean()-.5)<1e-4
    assert audit.residual_pp.abs().max()<.001
    assert (sol>=0).all() and (sol<=1).all()


def test_recent_monthly_count_inversion_exact_window():
    cal=pd.date_range('2021-01-01',periods=6,freq='MS')
    src=pd.DataFrame({'period_start':cal[:4], 'period_end':cal[2:],
        'informality_rate':[.4]*4,'occupied_thousands':[10]*4,
        'informal_thousands':[4]*4,'eligible_for_training':[True]*4,
        'concept':['Bogotá D.C.']*4,'definition':[NEW]*4,'domain':['city']*4})
    out, audit=_city_windows(src,NEW,cal,.01)
    assert list(out)==[11]
    assert np.allclose(out[11],.4,atol=1e-10)
    assert audit.informal_count_residual_persons.abs().max()<1e-6
    assert audit.employed_count_residual_persons.abs().max()<1e-6
    assert not audit.is_exact_official_monthly.any()


def test_recent_requires_complete_windows():
    cal=pd.date_range('2021-01-01',periods=6,freq='MS')
    src=pd.DataFrame({'period_start':cal[:3], 'period_end':cal[2:5],
        'informality_rate':[.4]*3,'occupied_thousands':[10]*3,
        'informal_thousands':[4]*3,'eligible_for_training':[True]*3,
        'concept':['Bogotá D.C.']*3,'definition':[NEW]*3,'domain':['city']*3})
    with pytest.raises(ValueError,match='Incomplete'):
        _city_windows(src,NEW,cal,.01)
