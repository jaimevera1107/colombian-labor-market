import pandas as pd
from icml.operations.integral import compare_candidate


def test_departmental_residual_share_is_a_count_in_people(tmp_path):
    a = tmp_path/'before.csv';b = tmp_path/'candidate.csv'
    pd.DataFrame([{'period':'2021-01','dep_code':11,
        'unemployed_residual_share':-15771.102192,
        'unemployment_rate':.209}]).to_csv(a,index=False)
    pd.DataFrame([{'period':'2021-01','dep_code':11,
        'unemployed_residual_share':-15771.102188,
        'unemployment_rate':.209}]).to_csv(b,index=False)
    report = compare_candidate({'labor.departamentos':a}, {'labor.departamentos':b})['labor.departamentos']
    assert report['status']=='EQUIVALENT_WITHIN_TOLERANCES'
    from icml.operations.integral import COUNT_TOLERANCE, RATE_TOLERANCE
    assert report['numeric_absolute_tolerances']['unemployed_residual_share']==COUNT_TOLERANCE
    assert report['numeric_absolute_tolerances']['unemployment_rate']==RATE_TOLERANCE


def test_dimensionless_rate_still_fails_on_drift(tmp_path):
    a=tmp_path/'before.csv';b=tmp_path/'candidate.csv'
    pd.DataFrame([{'period':'2021-01','dep_code':11,'unemployment_rate':.209}]).to_csv(a,index=False)
    pd.DataFrame([{'period':'2021-01','dep_code':11,'unemployment_rate':.209001}]).to_csv(b,index=False)
    r=compare_candidate({'labor.departamentos':a},{'labor.departamentos':b})['labor.departamentos']
    assert r['status']=='MISMATCH'
    assert 'numeric_tolerance_exceeded' in r['issues']
