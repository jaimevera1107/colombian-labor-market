"""H34 regression gates for mandatory Excel-first integral execution."""
import csv
from pathlib import Path

import pytest

from icml.operations.prepared_sources import (
    NON_MODEL_COMPARATORS, _merge_macro, stage_labor_source_view, sha256,
)


def make_macro(path: Path, *, revised=False):
    keys = ['date','year','month']
    fields = ['exchange_rate','producer_price_index','consumer_price_index',
              'inflation_rate','industrial_production_index','real_value_unit_uvr','vacancies']
    frozen = keys + fields + list(NON_MODEL_COMPARATORS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as fd:
        writer = csv.DictWriter(fd, fieldnames=keys + fields if revised else frozen)
        writer.writeheader()
        for i in range(132):
            year, month = 1993 + i // 12, 1 + i % 12
            row = dict(date=f'{year:04d}-{month:02d}-01',year=str(year),month=str(month))
            row.update({k: str(i + j + (1 if revised and i == 5 and j == 0 else 0))
                        for j,k in enumerate(fields)})
            if not revised:
                row.update({k:'123.0' for k in NON_MODEL_COMPARATORS})
            writer.writerow(row)


def test_macro_from_excel_keeps_only_frozen_comparison_fields(tmp_path):
    old, generated, target = [tmp_path / x for x in ('old.csv','excel.csv','stage.csv')]
    make_macro(old)
    make_macro(generated, revised=False)
    # The seven Excel fields have their own expected values; no vintage changed.
    with generated.open(encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    with generated.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])[:10]);w.writeheader();w.writerows(
            [{k:r[k] for k in list(rows[0])[:10]} for r in rows])
    digest=sha256(old)
    report=_merge_macro(old, generated, target)
    assert report['rows']==132
    assert sha256(old)==digest
    with target.open(encoding='utf-8-sig') as f:
        result=list(csv.DictReader(f))
    assert set(NON_MODEL_COMPARATORS).issubset(result[0])
    assert result[5]['exchange_rate']==rows[5]['exchange_rate']
    assert result[5]['employed_spliced']=='123.0'


def test_macro_rejects_changed_excel_values(tmp_path):
    old, generated = tmp_path/'old.csv', tmp_path/'external.csv'
    make_macro(old)
    make_macro(generated, revised=True)
    with pytest.raises(ValueError,match='Updated economic values differ'):
        _merge_macro(old, generated, tmp_path/'dest.csv')
    assert not (tmp_path/'dest.csv').exists()


def test_no_source_view_if_declared_file_missing(tmp_path):
    cfg = tmp_path / 'configs'
    cfg.mkdir()
    for name in ('national','urban','departmental','integration'):
        (cfg / f'{name}.toml').write_text(
            f'[{name}.sources]\nexample = "insumos/missing.csv"\n',encoding='utf-8')
    with pytest.raises(ValueError,match='no longer consumes expected'):
        stage_labor_source_view(tmp_path, tmp_path/'pre', cfg, tmp_path.parent/'h34_outside')
    assert not (tmp_path.parent/'h34_outside').exists()
