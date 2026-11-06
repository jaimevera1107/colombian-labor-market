"""Guard the RC2 reviewed Pareto donor decisions against silent monthly changes.

The frozen selection uses 2021-2024 proxies and 2025 diagnostics. Updating
2026 or later observations never changes that locked selection context.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


class FrozenDonorError(ValueError):
    """The verified urban Pareto study no longer matches current inputs."""


def _hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def selection_context_hash(proxies: pd.DataFrame, years: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)) -> str:
    """Hash exactly the fixed reference years, not future publication months."""
    subset=proxies.loc[proxies['year'].isin(years)].sort_values(['dep_code','year'])
    fields=sorted(x for x in subset.columns if x not in ('dep_code','year'))
    rows=[]
    for row in subset.to_dict('records'):
        rows.append([int(row['dep_code']),int(row['year']),*[format(float(row[k]),'.17g') if isinstance(row[k],(float,int)) else str(row[k]) for k in fields]])
    payload=json.dumps({'fields':fields,'rows':rows},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return _hash_bytes(payload)


def policy_hash(policy: Any) -> str:
    payload=json.dumps(asdict(policy),sort_keys=True,separators=(',',':')).encode('utf-8')
    return _hash_bytes(payload)


def frozen_manifest(proxies: pd.DataFrame, policy: Any, historical: Path, reference: Path, selected: dict[int,int]) -> dict[str,Any]:
    return {
        'method':'Pareto five criteria with holdout and seam guards (RC2)',
        'study':'fases/02_ciudades/docs/02_ESTUDIO_PARETO_EVIDENCIA.md',
        'status':'FROZEN_RESEARCH_SELECTION',
        'reference_years':[2021,2022,2023,2024,2025],
        'proxy_context_sha256':selection_context_hash(proxies),
        'policy_sha256':policy_hash(policy),
        'historical_signals_sha256':_hash_bytes(historical.read_bytes()),
        'reference_donors_sha256':_hash_bytes(reference.read_bytes()),
        'selected_donors':{str(k):int(v) for k,v in sorted(selected.items())},
    }


def verify_frozen(manifest_path: Path, proxies: pd.DataFrame, policy: Any,
                  historical: Path, reference: Path, selected: dict[int,int]) -> None:
    """Fail closed when history, decision rule or assignments have changed."""
    if not manifest_path.is_file():
        raise FrozenDonorError(f'Missing mandatory frozen donor manifest: {manifest_path}')
    actual=frozen_manifest(proxies,policy,historical,reference,selected)
    saved=json.loads(manifest_path.read_text(encoding='utf-8'))
    for key in ('proxy_context_sha256','policy_sha256',
                'historical_signals_sha256','reference_donors_sha256','selected_donors'):
        if actual[key]!=saved.get(key):
            raise FrozenDonorError(f'Frozen Pareto donor mismatch in {key}; requires methodological revision')
