"""Fail-closed H23 orchestration; no test ever publishes an ICML vintage."""
from pathlib import Path

import pytest

from tests.annexes import annex
from icml.operations import h23
from icml.operations.h23 import prepare_monthly_cycle, verify_monthly_cycle


def _root(tmp_path):
    root = tmp_path / 'frozen'
    (root / 'datos/2_procesamiento/productos_congelados/pruebas_calidad').mkdir(parents=True)
    (root / 'datos/2_procesamiento/productos_congelados/pruebas_calidad/nacionales.csv').write_text(
        'period,employed\n2026-07,123\n2026-08,124\n', encoding='utf-8')
    return root


def _integrity():
    return {'status': 'PASS_FROZEN_FILE_INTEGRITY', 'issues': [],
            'checked_count': 8,
            'products': [{'product': f'product.{i}', 'sha256': 'a'*64} for i in range(8)]}


@pytest.fixture
def monkey_integrity(monkeypatch):
    monkeypatch.setattr(h23, 'verify_products', lambda root: _integrity())


def test_missing_pair_creates_only_non_executable_audit(tmp_path, monkey_integrity):
    root = _root(tmp_path)
    report = prepare_monthly_cycle(root, '2026-09', tmp_path/'cycle')
    assert report['status'] == 'BLOCKED_FOR_MONTHLY_COMPUTATION_AND_PUBLICATION'
    assert report['required_sources']['expected_social_security_start_month'] == '2026-07'
    assert not report['publication_permitted']
    assert not report['computation_performed']
    assert (tmp_path/'cycle'/'23_monthly_cycle.json').is_file()
    assert (tmp_path/'cycle'/'23_geih_observations.csv').read_text().count('\n') == 1
    assert verify_monthly_cycle(root, tmp_path/'cycle')['status'] == 'PASS_INTAKE_EVIDENCE_ONLY'


def test_metadata_coherent_fake_files_still_block(tmp_path, monkey_integrity):
    root = _root(tmp_path)
    geih = tmp_path/'labor.xlsx';geih.write_bytes(b'not an official workbook')
    social = tmp_path/'social.xlsx';social.write_bytes(b'not an official workbook')
    report = prepare_monthly_cycle(root, '2026-09', tmp_path/'cycle', geih, social,
                                   '2026-09','2026-07','2026-09')
    assert report['required_sources']['status'].startswith('PAIR_CALENDAR_COHERENT')
    assert 'GEIH_WORKBOOK_CONTENT_VALIDATION_FAILED' in report['blockers']
    assert 'SOCIAL_SECURITY_XLSX_CONTENT_VALIDATION_FAILED' in report['blockers']
    assert not report['publication_permitted']
    assert verify_monthly_cycle(root, tmp_path/'cycle')['status'] == 'PASS_INTAKE_EVIDENCE_ONLY'
    (tmp_path/'cycle'/'sources'/'geih.xlsx').write_bytes(b'tampered')
    assert 'STAGED_SOURCE_HASH_MISMATCH_geih' in verify_monthly_cycle(root, tmp_path/'cycle')['issues']


def test_mismatched_quarter_and_invalid_target_block(tmp_path, monkey_integrity):
    root = _root(tmp_path)
    geih = tmp_path/'labor.xlsx';geih.write_bytes(b'invalid')
    social = tmp_path/'social.xlsx';social.write_bytes(b'invalid')
    report = prepare_monthly_cycle(root, '2026-09', tmp_path/'cycle', geih, social,
                                   '2026-09','2026-06','2026-08')
    assert 'SOCIAL_SECURITY_WINDOW_MISMATCH' in report['blockers']
    with pytest.raises(ValueError):
        h23._month('2026-13')
    candidate = prepare_monthly_cycle(root,'2026-10',tmp_path/'not-next')
    assert 'NOT_NEXT_CONTIGUOUS_MONTH' in candidate['blockers']


def test_output_is_immutable_and_outside_bundle(tmp_path, monkey_integrity):
    root = _root(tmp_path)
    destination = tmp_path/'cycle'
    prepare_monthly_cycle(root, '2026-09', destination)
    with pytest.raises(FileExistsError):
        prepare_monthly_cycle(root, '2026-09', destination)
    with pytest.raises(ValueError):
        prepare_monthly_cycle(root, '2026-09', root/'cycle')


def test_product_integrity_failure_blocks(tmp_path, monkeypatch):
    root = _root(tmp_path)
    bad = _integrity()
    bad['issues'] = [{'error': 'sha256_mismatch'}]
    monkeypatch.setattr(h23, 'verify_products', lambda root: bad)
    report = prepare_monthly_cycle(root, '2026-09', tmp_path/'cycle')
    assert 'FROZEN_PRODUCT_INTEGRITY_FAILED' in report['blockers']
    assert 'FROZEN_PRODUCTS_CHANGED' in verify_monthly_cycle(root, tmp_path/'cycle')['issues']


def test_cli_fail_closed_even_when_no_files(tmp_path, monkey_integrity):
    from icml.cli import main
    root = _root(tmp_path)
    assert main(['operations','monthly-cycle','--root',str(root),
                 '--period','2026-09','--output',str(tmp_path/'cycle')]) == 2
    assert main(['operations','verify-monthly-cycle','--root',str(root),
                 '--cycle',str(tmp_path/'cycle')]) == 0


def test_real_august_pair_is_content_validated_but_never_published(tmp_path, monkeypatch, monkey_integrity):
    # Simulate a prior July research checkpoint solely for source-intake test;
    # this does NOT create or change any actual ICML frozen vintage.
    from icml.operations import h23
    root = _root(tmp_path)
    (root/'datos/2_procesamiento/productos_congelados/pruebas_calidad/nacionales.csv').write_text(
        'period,employed\n2026-06,123\n2026-07,124\n', encoding='utf-8')
    monkeypatch.setattr(h23, 'FROZEN_CUTOFF', '2026-07')
    checkpoint = Path(__file__).resolve().parents[3]
    geih = annex('mercado_laboral', '2026-08')
    social = annex('informalidad', '2026-08')
    report = prepare_monthly_cycle(root, '2026-08', tmp_path/'cycle', geih, social,
                                   '2026-08', '2026-06', '2026-08')
    assert report['social_content_validation'].startswith('PASS_H35_')
    assert report['geih_content_validation'].startswith('PASS_H22_')
    assert report['social_observation_rows'] == 5
    assert 'SOCIAL_SECURITY_XLSX_CONTENT_NOT_VERIFIED' not in report['blockers']
    assert 'CANONICAL_SOURCE_ADAPTER_NOT_VERIFIED' in report['blockers']
    assert report['status'] == 'BLOCKED_FOR_MONTHLY_COMPUTATION_AND_PUBLICATION'
    assert not report['publication_permitted']
    assert verify_monthly_cycle(root, tmp_path/'cycle')['status'] == 'PASS_INTAKE_EVIDENCE_ONLY'
    assert verify_monthly_cycle(root, tmp_path/'cycle')['source_content_social_verified'] is True
