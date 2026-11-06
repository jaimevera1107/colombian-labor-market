"""Recompute H5 and H6 from original DANE Excel-derived observations.

H5: national latent inversion of rolling 3-month informality sources.
H6: 13 city -> national -> 23 city -> 33 city sequential reconstruction.
These are current-vintage source/model steps. They DO NOT re-train the selected
CNPV/MLP departmental model, which remains a model artifact of the August
research vintage. Every rebuilt H5/H6 candidate is compared with the frozen
selected artifacts before H9 may use it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from icml.domain.cutoff import (
    ACTIVE_CUTOFF,
    FROZEN_CUTOFF,
    INFORMALITY_NEW_FIRST_MONTH,
    expected_month_count,
)
from icml.informality.national import InformalityNationalPipeline, load_informality_config
from icml.informality.sequential import run as sequential_run
from icml.io.artifacts import ArtifactStore
from icml.operations.integral import compare_candidate


def _compare_h5(frozen: Path, built: Path) -> dict:
    n_months = expected_month_count(INFORMALITY_NEW_FIRST_MONTH)
    old, new = pd.read_csv(frozen), pd.read_csv(built)
    if set(old.columns) != set(new.columns) or len(old) != n_months or len(new) != n_months:
        raise ValueError('H5 regenerated monthly schema/coverage changed')
    if old.period.duplicated().any() or new.period.duplicated().any():
        raise ValueError('H5 duplicate monthly period')
    left = old.set_index('period').sort_index()
    right = new.set_index('period').sort_index()
    if not left.index.equals(right.index):
        raise ValueError('H5 monthly keys changed')
    numbers = {}
    for field in left.columns:
        a,b = left[field],right[field]
        if pd.api.types.is_bool_dtype(a) or pd.api.types.is_bool_dtype(b):
            if not a.equals(b):
                raise ValueError(f'H5 boolean source attribute changed: {field}')
        elif pd.api.types.is_numeric_dtype(a):
            if not np.isfinite(a).all() or not np.isfinite(b).all():
                raise ValueError(f'H5 nonfinite numeric source: {field}')
            diff = float((a-b).abs().max())
            limit = 1e-8 if 'rate' in field else 1e-3
            numbers[field] = diff
            if diff > limit:
                raise ValueError(f'H5 new-vs-frozen {field}: {diff}>{limit}')
        elif not a.fillna('<NULL>').equals(b.fillna('<NULL>')):
            raise ValueError(f'H5 categorical evidence changed: {field}')
    return {'status': 'PASS', 'rows': n_months, 'max_numeric_difference': numbers}


def run(root: Path, prepared: Path, labor_quality: Path, output: Path,
        *, strict_reference: bool | None = None, strict_from: str | None = None) -> dict:
    """Rebuild H5 and H6 and compare them with the frozen selected stage.

    The comparison is a hard gate only for the frozen vintage. For any other
    cutoff the rebuilt series legitimately differ from the frozen ones (each
    new window re-identifies the latent months from 2021), so the differences
    are recorded in the manifest instead of stopping the run.

    ``strict_from`` (``YYYY-MM``) narrows the hard gate of the frozen vintage
    to the months from there on. It is used when a splice changes the labor
    levels before that month on purpose: nothing may change from then on, and
    the full comparison is still recorded in the manifest.
    """
    if strict_reference is None:
        strict_reference = ACTIVE_CUTOFF == FROZEN_CUTOFF
    root,prepared,labor_quality,output=map(lambda x: Path(x).resolve(),
                                          (root,prepared,labor_quality,output))
    if output.exists():
        raise FileExistsError('Recomputed H5/H6 staging must be new')
    if output == root or root in output.parents:
        raise ValueError('Never regenerate into the frozen checkpoint')
    source = prepared/'h29/informality_source_observations.csv'
    if not source.is_file():
        raise FileNotFoundError(source)
    config = root/'configs/rc1'
    h5=output/'h5'
    policy=load_informality_config(config/'informality.toml')
    InformalityNationalPipeline(policy).run(source.parent,
        ArtifactStore(labor_quality.parent), ArtifactStore(h5))
    recent=h5/'candidates/national_informality_monthly_2021_2026.csv'
    frozen_recent = root/'datos/2_procesamiento/fuentes_preparadas/informalidad/national_informality_monthly_2021_2026.csv'
    try:
        recent_audit = _compare_h5(frozen_recent, recent)
    except ValueError as exc:
        if strict_reference:
            raise
        recent_audit = {'status': 'DIFFERS_FROM_FROZEN_VINTAGE', 'detail': str(exc)}
    h6=output/'h6'
    seq=sequential_run(source,labor_quality/'ciudades.csv',
        labor_quality/'departamentos.csv',labor_quality/'nacionales.csv',recent,
        root/'datos/2_procesamiento/fuentes_preparadas/anclas_dane/anclas_dane_agregado_13_areas_2001_2009.csv',
        h6,config/'informality_sequential.toml')
    paths = {
        'informalidad.nacionales':'02_nacionales.csv',
        'informalidad.ciudades':'03_ciudades_33.csv',
    }
    baseline={k:root/'datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6'/filename for k,filename in paths.items()}
    candidates={k:h6/filename for k,filename in paths.items()}
    comparisons=compare_candidate(baseline,candidates)
    gate=comparisons
    if strict_from is not None and strict_reference:
        gate=strict_window_gate(baseline,candidates,strict_from,output/'strict_window')
    if strict_reference and any(
            x.get('status')!='EQUIVALENT_WITHIN_TOLERANCES' for x in gate.values()
        ):
        raise ValueError('H6 regenerated series differ from frozen selected stage; see staged files')
    manifest={'status':'PASS', 'strict_reference':strict_reference, 'strict_from':strict_from,
              **({'window_comparison_with_frozen':gate} if gate is not comparisons else {}),
              'H5':recent_audit, 'H6':{
        'hard_gates_passed':seq['hard_gates_passed'],
        'thirteen_city_rows':seq['n_13'],
        'national_rows':seq['n_national'],
        'thirty_three_city_rows':seq['n_33'],
        'comparison_with_frozen':comparisons},
        'full_h9_departmental_mlp_retrained':False,
        'frozen_census_transfer_and_mlp_priors_retained':True,
        'publishes_new_vintage':False}
    (output/'35_H5_H6_REGENERATION.json').write_text(
         json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return manifest


def strict_window_gate(baseline: dict, candidates: dict, strict_from: str, window: Path) -> dict:
    """Compare frozen and rebuilt H5/H6 tables only from ``strict_from`` onwards.

    Before that month the labor reconstruction (2.4.0) legitimately changes
    the history, so the hard gate of the frozen vintage applies to the
    anchored stretch only. Both sides are cut to the window and written
    next to each other for inspection; the comparison is the usual
    tolerance-based one.
    """
    window=Path(window); window.mkdir(parents=True,exist_ok=False)
    frozen_window,rebuilt_window={},{}
    for key in baseline:
        filename=Path(baseline[key]).name
        for source_path,store,tag in ((baseline[key],frozen_window,'frozen'),
                                      (candidates[key],rebuilt_window,'rebuilt')):
            table=pd.read_csv(source_path,dtype=str,keep_default_na=False)
            target=window/f'{tag}_{filename}'
            table[table['period']>=strict_from].to_csv(target,index=False,lineterminator='\n')
            store[key]=target
    return compare_candidate(frozen_window,rebuilt_window)
