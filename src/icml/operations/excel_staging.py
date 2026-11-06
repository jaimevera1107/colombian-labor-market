"""H31 transactional staging of every historically verified Excel extractor.

This is a *source-preparation* process, not a statistical rerun or vintage
promotion. Unknown legacy processed sources are preserved separately.
"""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from icml.domain.cutoff import ACTIVE_CUTOFF
from icml.operations.excel_sources import run as h29
from icml.operations.excel_historical_sources import run as h31


def run(root: Path, output: Path) -> dict:
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    if root==output or root in output.parents:
        raise ValueError('Staging must be outside frozen checkpoint')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.icml_excel_stage_',dir=output.parent,ignore_cleanup_errors=True) as temp:
        stage=Path(temp)
        one=h29(root,stage/'h29',verify=True)
        two=h31(root,stage/'h31')
        status='PASS' if one['status']=='PASS' and two['status']=='PASS' else 'BLOCKED'
        summary={'status':status,'reference_month':ACTIVE_CUTOFF,
                 'verified_generators':9,'h29':one, 'h31':two,
                 'not_generated_from_primary_excel':[
                   'the six *_spliced columns in indicadores_mensuales_1993_2003.csv'],
                 'preserves_originals_and_frozen_products':True,
                 'publishes_new_vintage':False}
        if status!='PASS':raise ValueError('One or more Excel generators failed')
        (stage/'PREPARACION_UNIFICADA_H31.json').write_text(
            json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # os.rename fails on Windows if the target exists or across devices; shutil.move is cross-platform.
        import shutil as _shutil
        _shutil.move(str(stage), str(output))
    return summary
