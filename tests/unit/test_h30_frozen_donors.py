"""H30 frozen-study and lineage regression guards."""
import json
from pathlib import Path

import pandas as pd
import pytest

from icml.urban.frozen_donors import (
    FrozenDonorError, frozen_manifest, selection_context_hash, verify_frozen,
)


def test_2026_updates_do_not_change_locked_reference_hash():
    p=pd.DataFrame({'dep_code':[81,81,81], 'year':[2024,2025,2026],
                    'employed':[10.,12.,14.], 'city':['A','A','A']})
    old=selection_context_hash(p)
    p.loc[p.year==2026,'employed']=999.
    assert selection_context_hash(p)==old


def test_historical_revision_changes_locked_reference_hash():
    p=pd.DataFrame({'dep_code':[81,81], 'year':[2024,2025], 'employed':[10.,12.]})
    old=selection_context_hash(p)
    p.loc[p.year==2024,'employed']=999.
    assert selection_context_hash(p)!=old


def test_frozen_donor_guard_rejects_changed_assignment(tmp_path):
    a=tmp_path/'history.csv';b=tmp_path/'reference.csv'
    a.write_text('original');b.write_text('reference')
    p=pd.DataFrame({'dep_code':[81], 'year':[2024], 'employed':[10.]})
    class Policy:
        pass
    from dataclasses import dataclass
    @dataclass
    class P:
        n:int=1
    policy=P()
    manifest=frozen_manifest(p,policy,a,b,{81:63})
    path=tmp_path/'frozen.json';path.write_text(json.dumps(manifest))
    verify_frozen(path,p,policy,a,b,{81:63})
    with pytest.raises(FrozenDonorError, match='selected_donors'):
        verify_frozen(path,p,policy,a,b,{81:50})
    with pytest.raises(FrozenDonorError, match='policy_sha256'):
        verify_frozen(path,p,P(2),a,b,{81:63})


def test_h30_canonical_manifest_contains_research_decisions():
    root=Path(__file__).resolve().parents[2]
    p=root/'datos/2_procesamiento/fuentes_preparadas/urbano/donantes_pareto_congelados_h30.json'
    if not p.exists():
        pytest.skip('H30 research source root is not in this installation')
    obj=json.loads(p.read_text())
    assert len(obj['selected_donors'])==9
    assert obj['selected_donors']['91']==17
    assert obj['selected_donors']['97']==63
