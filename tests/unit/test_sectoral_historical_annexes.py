"""Regression gates preventing false historic monthly anchors."""
import hashlib
import pandas as pd
import pytest
from icml.sectoral.historical_annexes import publication_inventory,validate_annex_observations,run


def sample(tmp_path):
    orig=tmp_path/'anexo_test.xls';orig.write_bytes(b'original archive of demonstrative rows')
    return pd.DataFrame([{
        'source_id':'sample','source_file':'anexo_test.xls',
        'source_sha256':hashlib.sha256(orig.read_bytes()).hexdigest(),
        'source_url':'https://www.dane.gov.co/test', 'domain':'total_nacional_GEIH',
        'ciiu_revision':'CIIU_Rev4_AC','source_branch':'A',
        'mapped_sector_code':'A','mapping_status':'DIRECT_VERIFIED',
        'source_review_status':'REVIEWED_OFFICIAL_ANNEX',
        'period_start':'2015-01','period_end':'2015-01','temporal_support':'calendar_month',
        'value':'23.5','unit':'thousands_persons'}])


def test_inventory_distinguishes_listing_from_evidence():
    c=publication_inventory()
    assert len(c)==70
    assert c.publication_period.min()=='2007-04'
    assert c.publication_period.max()=='2014-12'
    assert c.month_observed.sum()==0
    assert c.annex_locally_parsed.sum()==0


def test_rolling_not_mislabeled_month(tmp_path):
    x=sample(tmp_path);x.loc[0,'period_start']='2014-10';x.loc[0,'period_end']='2014-12'
    with pytest.raises(ValueError,match='VENTANA_INCOMPATIBLE'):
        validate_annex_observations(x,tmp_path)
    x.loc[0,'temporal_support']='moving_3m'
    result=validate_annex_observations(x,tmp_path)
    assert result.eligible_anchor.all() and not result.monthly_direct.any()


def test_sha_and_support_verification(tmp_path):
    x=sample(tmp_path)
    unchecked=validate_annex_observations(x)
    assert not unchecked.eligible_anchor.any()
    verified=validate_annex_observations(x,tmp_path)
    assert verified.eligible_anchor.all() and verified.monthly_direct.all()
    assert verified.value_persons.iloc[0]==23500
    x.loc[0,'source_sha256']='0'*64
    with pytest.raises(ValueError,match='HASH_FUENTE_NO_COINCIDE'):
        validate_annex_observations(x,tmp_path)


def test_no_harmonization_when_ambiguous(tmp_path):
    x=sample(tmp_path);x.loc[0,'mapping_status']='AGGREGATE_ONLY'
    with pytest.raises(ValueError,match='NO_ASIGNAR_CODIGO'):
        validate_annex_observations(x,tmp_path)


def test_no_fabricated_historic_rows(tmp_path):
    recent=pd.DataFrame([{'period':'2015-01','sector_code':'A','employed_persons':100,
                          'temporal_support':'calendar_month','window_months':1}]);
    source=tmp_path/'r.csv';recent.to_csv(source,index=False)
    res=run(tmp_path/'output',source)
    assert res['historic_verified_rows']==0
    c=pd.read_csv(tmp_path/'output'/'10_cobertura_sectorial_1993_2026.csv')
    assert len(c)==404
    assert not c.full_14_direct_observed.any()
    assert not (c.loc[c.period=='2007-04','historical_verified_direct_group_count']>0).any()
