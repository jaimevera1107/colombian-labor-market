"""H29 Excel source preparation contract tests, including frozen-data parity."""
import csv
from pathlib import Path

import pytest

from icml.cli import main
from icml.operations.excel_sources import _compare, run, SourceFormatError, _file


def _checkpoint_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_sources_reproduce_frozen_canonical_inputs(tmp_path):
    root = _checkpoint_root()
    if not (root / 'datos/1_ingesta/excel_originales').is_dir():
        pytest.skip('Full historic Excel source bundle not present in lightweight checkout')
    result = run(root, tmp_path/'stage')
    assert result['status'] == 'PASS'
    assert sorted(v['rows'] for v in result['components'].values()) == [12, 3542, 4752, 6580, 7920]
    assert all(v['equivalent'] is True for v in result['components'].values())
    assert all(v['max_absolute_difference'] == 0 for k,v in result['components'].items() if k != 'informality')


def test_no_source_overwrites_and_staging_outside_checkpoint(tmp_path):
    root = _checkpoint_root()
    with pytest.raises(ValueError, match='outside checkpoint'):
        run(root, root/'should_not_write')


def test_compare_rejects_changed_numeric_data(tmp_path):
    baseline=tmp_path/'baseline.csv'
    with baseline.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['place','year','value'])
        w.writeheader();w.writerow({'place':'Antioquia','year':'2024','value':'10'})
    report=_compare([{'place':'Antioquia','year':'2024','value':'11'}],baseline,('value',))
    assert report['equivalent'] is False
    assert report['numeric_differences_over_1e_9']==1


def test_source_accepts_only_xlsx(tmp_path):
    (tmp_path/'legacy.xls').write_bytes(b'not original xlsx')
    with pytest.raises(SourceFormatError,match='Expected original'):
        _file(tmp_path,'legacy.xls')


def test_cli_has_source_preparation():
    assert callable(main)


def test_manifest_rejects_changed_source_before_extraction(tmp_path):
    """A changed Excel never inherits the old source's approval."""
    import json
    from icml.operations.excel_sources import _roles
    root=tmp_path/'project'
    catalog=root/'datos/2_procesamiento/catalogos/REGISTRO_EXCEL_ORIGINALES_H29.json'
    catalog.parent.mkdir(parents=True)
    original=root/'datos/1_ingesta/excel_originales/test.xlsx'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'changed')
    catalog.write_text(json.dumps({'active_roles':{
        'test':{'path':'datos/1_ingesta/excel_originales/test.xlsx',
                'sha256':'0'*64}}}))
    with pytest.raises(SourceFormatError, match='Hash mismatch'):
        _roles(root)


def test_manifest_rejects_traversal_path(tmp_path):
    """Source manifest must not point outside the approved root."""
    import json
    from icml.operations.excel_sources import _roles
    root=tmp_path/'project'
    catalog=root/'datos/2_procesamiento/catalogos/REGISTRO_EXCEL_ORIGINALES_H29.json'
    catalog.parent.mkdir(parents=True)
    external=tmp_path/'external.xlsx'
    external.write_bytes(b'external')
    catalog.write_text(json.dumps({'active_roles':{
        'external':{'path':'../external.xlsx','sha256':'0'*64}}}))
    with pytest.raises(FileNotFoundError):
        _roles(root)
