"""Verify frozen national margins and KL parity for experimental calibration.

Usage: python scripts/verify_informality_frontier.py <frontier_folder> <legacy_closures_folder>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def verify(folder: Path, root: Path) -> dict:
    f=pd.read_csv(folder/'10_calibrated_all_candidates_EXPERIMENTAL.csv')
    monthly=pd.read_csv(folder/'10_monthly_metrics.csv')
    if f.duplicated(['candidate','variant','period','dep_code']).any():
        raise AssertionError('Duplicated experimental key')
    if f[['rate_prior','rate_calibrated','employed','informal','formal','factor_employed']].isna().any().any():
        raise AssertionError('Missing numerical outcome')
    if (f.rate_calibrated.lt(0)|f.rate_calibrated.gt(1)).any():
        raise AssertionError('Out-of-range rates')
    if np.max(abs(f.informal+f.formal-f.employed))>1e-5:
        raise AssertionError('Local employment identity broken')
    if monthly.icml_residual_people.abs().max()>.01 or monthly.dane_residual_people.abs().max()>.01:
        raise AssertionError('National margin residual too large')
    oldparity={}
    for candidate in ('urban_direct','mlp_residual_92','mlp_shared19'):
        old=pd.read_csv(root/candidate/'08_department_informality_CALIBRATION_EXPERIMENTAL.csv')
        new=f[(f.candidate==candidate)&(f.variant=='kl_original')]
        if len(old)!=len(new):raise AssertionError('KL rows differ')
        m=old.merge(new,on=['dep_code','period'],validate='one_to_one',suffixes=('_old','_new'))
        dr=float(np.max(abs(m.rate_calibrated_old-m.rate_calibrated_new)))
        de=float(np.max(abs(m.employed_old-m.employed_new)))
        oldparity[candidate]={'max_rate_abs_diff':dr,'max_employed_abs_diff':de,'rows':len(m)}
        if dr>1e-9 or de>.01:raise AssertionError('Old KL not reproduced')
    return {'status':'PASS','experiments':f.groupby(['candidate','variant']).ngroups,
            'rows':len(f),'monthly_constraints':len(monthly),
            'max_national_icml_residual_people':float(monthly.icml_residual_people.abs().max()),
            'max_national_dane_residual_people':float(monthly.dane_residual_people.abs().max()),
            'legacy_parity':oldparity}


if __name__=='__main__':
    print(json.dumps(verify(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
