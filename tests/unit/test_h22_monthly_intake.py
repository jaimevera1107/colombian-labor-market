"""H22: source staging never promotes official monthly numbers to ICML estimates."""
from pathlib import Path
import pytest
from icml.operations.geih_intake import (
    monthly_column, validate_observation, prepare_intake, inspect_annex
)

FIXTURE = {
    'participation_rate_pct': 63.8, 'employment_rate_pct': 58.7,
    'unemployment_rate_pct': 8.0, 'population_thousands': 52000,
    'working_age_thousands': 40000, 'labor_force_thousands': 25520,
    'employed_thousands': 23478.4, 'unemployed_thousands': 2041.6,
    'inactive_thousands': 14480,
}

def test_month_column_and_boundary():
    assert monthly_column('2001-01') == 'B'
    assert monthly_column('2026-08') == 'KW'
    assert monthly_column('2026-09') == 'KX'
    with pytest.raises(ValueError): monthly_column('2000-12')


def test_invalid_identity_is_rejected():
    wrong=FIXTURE.copy()
    wrong['labor_force_thousands']+=100
    with pytest.raises(ValueError,match='labor-force identity'):
        validate_observation(wrong,'DANE_NACIONAL','2026-09')


def test_announced_rates_are_a_second_independent_check():
    wrong=FIXTURE.copy()
    wrong['participation_rate_pct']=70.0
    # Maintaining accounting doesn't make mismatched bulletin values acceptable.
    with pytest.raises(ValueError):
        validate_observation(wrong,'DANE_NACIONAL','2026-09')


def test_source_missing_creates_blocked_non_destructive_report(tmp_path):
    base=tmp_path/'base'; data=base/'datos/2_procesamiento/productos_congelados/pruebas_calidad';data.mkdir(parents=True)
    (data/'nacionales.csv').write_text('protected\n',encoding='utf-8')
    out=tmp_path/'out'
    report=prepare_intake(base,out,'2026-09',None)
    assert report['status']=='BLOCKED_OFFICIAL_XLSX_NOT_AVAILABLE_LOCALLY'
    assert not report['canonical_updated']
    assert report['frozen_nationals_sha256_unchanged']
    assert (data/'nacionales.csv').read_text()=='protected\n'
    with pytest.raises(FileExistsError):prepare_intake(base,out,'2026-09',None)


def test_reject_invalid_file_and_preserve_original(tmp_path):
    base=tmp_path/'base'; data=base/'datos/2_procesamiento/productos_congelados/pruebas_calidad';data.mkdir(parents=True)
    (data/'nacionales.csv').write_text('protected\n')
    fake=tmp_path/'not_a_dane_annex.csv';fake.write_text('period,values\n2026-09,999')
    report=prepare_intake(base,tmp_path/'out','2026-09',fake)
    assert report['status']=='BLOCKED_SOURCE_VALIDATION_ERROR'
    assert report['reference_rows']==0
    assert not report['canonical_updated']
    assert (data/'nacionales.csv').read_text()=='protected\n'

def test_august_2026_real_geih_annex_parity_if_fixture_present():
    """Regression check against published source workbook values (no June/Sept substitute)."""
    root = Path(__file__).resolve().parents[2]
    annex = root/'datos/1_ingesta/geih_mercado_laboral/geih_mercado_laboral_2026-08.xlsx'
    if not annex.is_file():
        pytest.skip('Real August source is kept in the full research checkpoint')
    values = inspect_annex(annex,['2026-08'])
    assert len(values)==2
    national=next(r for r in values if r['domain']=='DANE_NACIONAL')
    cities=next(r for r in values if r['domain']=='DANE_13_CIUDADES')
    assert national['employment_rate_pct']==pytest.approx(57.3633100767746, abs=1e-8)
    assert national['unemployment_rate_pct']==pytest.approx(9.363679721589868, abs=1e-8)
    assert national['employed_thousands']==pytest.approx(23685.33769145597, abs=1e-7)
    assert cities['employment_rate_pct']==pytest.approx(59.76923270821972, abs=1e-8)
    with pytest.raises(ValueError,match='Cached cell value missing|month header expected Sep'):
        inspect_annex(annex,['2026-09'])


def test_geih_staging_does_not_override_social_security_requirement(tmp_path):
    base=tmp_path/'base'; data=base/'datos/2_procesamiento/productos_congelados/pruebas_calidad';data.mkdir(parents=True)
    (data/'nacionales.csv').write_text('unchanged\n')
    report=prepare_intake(base,tmp_path/'out','2026-09',None)
    assert report['monthly_update_requires_both_sources']
    assert not report['matching_social_security_annex_verified']
    assert not report['full_monthly_update_eligible']
    assert not report['new_vintage_publication_permitted']
    assert report['social_security_required_window']=='2026-07/2026-09'
