"""Evidence gate for the observed DANE inputs underlying frozen H9 latents.

Checks whether the already-selected 2021+ latent national source is anchored to
*observed monthly employed levels* in the original DANE Excel. Does NOT infer
new model rates or equate observed informality with modeled latent rates.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import json

import pandas as pd
from icml.domain.cutoff import ACTIVE_CUTOFF, INFORMALITY_NEW_FIRST_MONTH, RECENT_MONTHS, month_labels
from openpyxl import load_workbook

from .h35_social_annex import inspect_social_annex, _assert_header


def _informality_annex(root: Path) -> str:
    """Return the active informality annex named by the Excel role registry.

    The registry is the single place that says which annex is active, so a
    run for another cutoff reads its own annex instead of a fixed file name.
    """
    registry = root / 'datos/2_procesamiento/catalogos/REGISTRO_EXCEL_ORIGINALES_H29.json'
    try:
        return json.loads(registry.read_text(encoding='utf-8'))['active_roles']['informality_current']['path']
    except (FileNotFoundError, KeyError):
        from icml.ingestion.discovery import INFORMALITY, annex_for
        found = annex_for(root / 'datos/1_ingesta', INFORMALITY, ACTIVE_CUTOFF)
        return found.path.relative_to(root).as_posix()


def audit_national_h9_lineage(root: Path, annex: Path | None = None) -> dict:
    root = Path(root).resolve()
    original = Path(annex) if annex else root / _informality_annex(root)
    recent = root / 'datos/2_procesamiento/fuentes_preparadas/informalidad/national_informality_monthly_2021_2026.csv'
    national = root / 'datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6/02_nacionales.csv'
    social = inspect_social_annex(original, ACTIVE_CUTOFF)
    latents = pd.read_csv(recent)
    n = pd.read_csv(national)
    expected = month_labels(INFORMALITY_NEW_FIRST_MONTH)
    if len(latents) != len(expected) or latents.period.tolist() != expected:
        raise ValueError(
            f'Frozen H9 latent monthly source does not cover '
            f'{INFORMALITY_NEW_FIRST_MONTH}..{ACTIVE_CUTOFF}')
    target = n.loc[n.national_type == 'DANE_REFERENCIA',
                   ['period', 'employed_frozen', 'informality_rate_estimated']]
    joint = latents.merge(target, on='period', validate='one_to_one')
    if len(joint) != RECENT_MONTHS:
        raise ValueError(f'H9 national latent does not map one-to-one to all {RECENT_MONTHS} months')
    if joint.isna().any().any():
        raise ValueError('Missing monthly latent values')
    latent_diff = float((joint.employed_frozen-joint.employed_persons_fixed_dane).abs().max())
    rate_diff = float((joint.informality_rate_estimated-joint.informality_rate_latent).abs().max())
    if latent_diff > 1e-6 or rate_diff > 1e-9:
        raise ValueError('H9 frozen national level or latent rate differs from its source')
    wb = load_workbook(original, read_only=True, data_only=True, keep_links=False)
    try:
        sheet = wb['Grandes dominios ']
        observed = []
        for idx, period in enumerate(expected):
            column = idx + 2
            _assert_header(sheet.cell(13, column).value, period, 'month')
            val = sheet.cell(14, column).value
            if not isinstance(val, (float,int)) or not np.isfinite(val):
                raise ValueError(f'Missing official employed {period}')
            observed.append(float(val) * 1000)
    finally:
        wb.close()
    difference = float(np.max(np.abs(np.array(observed) -
                                      joint.employed_persons_fixed_dane.to_numpy(dtype=float))))
    # The archived H9 benchmark rounds employed levels to one decimal person.
    if difference > .501:
        raise ValueError(f'National employed differs from official GEIH: {difference} people')
    return {'status': 'PASS', 'months': RECENT_MONTHS,
            'source_workbook_sha256': social['sha256'],
            'official_monthly_employed_vs_H9_anchor_max_difference_people': difference,
            'H9_labor_anchor_max_difference_people': latent_diff,
            'H9_latent_rate_max_difference': rate_diff,
            'official_august_observed_informality_rate': social['observations'][0]['informality_rate'],
            'frozen_august_reconstructed_latent_rate': float(joint.informality_rate_latent.iloc[-1]),
            'observed_informality_rate_equals_latent_rate': False,
            'separate_model_layer_must_be_reestimated_for_new_vintage': True,
            'source_is_used_as_employed_level_anchor_not_as_official_latent_rate': True,
            'does_not_certify_new_month': True}
