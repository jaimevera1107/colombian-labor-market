"""Use the archived official Excel to catch stale, wrong-month, corrupt sources."""
from pathlib import Path

import pytest

from icml.operations.h35_social_annex import inspect_social_annex
from tests.annexes import annex
from icml.operations.h35_informality_lineage import audit_national_h9_lineage

ROOT = Path(__file__).resolve().parents[2]
SOURCE = annex('informalidad', '2026-08')


def test_official_august_workbook_checks_three_dane_signals():
    data = inspect_social_annex(SOURCE, '2026-08')
    assert data['status'] == 'PASS_SOURCE_CONTENT'
    assert data['three_month_window_start'] == '2026-06'
    assert len(data['observations']) == 5
    assert data['observations'][0]['reference_type'] == 'observed_monthly'
    assert data['observations'][2]['reference_type'] == 'rolling_three_months'
    assert data['social_security_rolling']['pension_contributors_are_not_identical_to_formal']
    assert not data['authorizes_publication']


def test_workbook_cannot_pretend_to_be_other_month():
    for month in ('2026-07', '2026-09'):
        with pytest.raises(ValueError, match='label|newer|Missing|invalid'):
            inspect_social_annex(SOURCE, month)


def test_non_xlsx_is_rejected(tmp_path):
    bad = tmp_path / 'fake.xlsx'
    bad.write_bytes(b'not a workbook')
    with pytest.raises(Exception):
        inspect_social_annex(bad, '2026-08')
    with pytest.raises(ValueError, match='xlsx'):
        inspect_social_annex(tmp_path/'fake.csv', '2026-08')


def test_h9_observed_employed_anchor_not_informal_rate():
    r = audit_national_h9_lineage(ROOT)
    assert r['status'] == 'PASS'
    assert r['months'] == 68
    assert r['official_monthly_employed_vs_H9_anchor_max_difference_people'] <= .501
    assert r['H9_latent_rate_max_difference'] < 1e-9
    assert r['official_august_observed_informality_rate'] != r['frozen_august_reconstructed_latent_rate']
    assert not r['observed_informality_rate_equals_latent_rate']
