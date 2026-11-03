"""H17 integration guards: canonical isolation and frozen H16 integrity."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from icml import __version__
from icml.pipeline.stage_registry import STAGE_SPECS
from icml.sectoral_integral import validate_bundle, run_predictor, export_experimental
from icml.sectoral_predictive import h16_integracion

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / 'datos' / '2_procesamiento' / 'sectorial_h16'


def test_integrated_version_and_stage_catalog():
    import tomllib
    declared = tomllib.loads((Path(__file__).resolve().parents[2] / 'pyproject.toml').read_text())['project']['version']
    assert __version__ == declared
    assert set(STAGE_SPECS) == {
        'national', 'urban', 'departmental', 'integration', 'modeling',
        'reconciliation', 'quality', 'informality', 'evaluation', 'census_bridge'
    }


def test_frozen_h16_manifest_and_accounting():
    report = validate_bundle(FROZEN)
    assert (report['months'], report['departments'], report['sectors'], report['cells']) == (404, 33, 15, 199980)
    assert report['max_department_full_error_persons'] < 1e-4
    assert report['max_national_sector_error_persons'] < 1e-4
    assert report['can_publish'] is False


def test_predictive_engine_import_and_h16_constraints():
    assert len(h16_integracion.ORIGINAL38) == 38
    assert len(h16_integracion.GROUPS) == 33
    a = np.array([[3., 1., 2.], [2., 3., 1.]])
    x,_ = h16_integracion.ipf(a, np.array([7., 13.]), np.array([8., 12., 0.]))
    assert np.allclose(x.sum(axis=1), [7., 13.], atol=1e-7)
    assert np.allclose(x.sum(axis=0), [8., 12., 0.], atol=1e-7)


def test_never_overwrite_frozen_bundle():
    with pytest.raises(ValueError, match='different'):
        run_predictor(FROZEN, FROZEN)


def test_guard_rejects_nonempty_output(tmp_path):
    (tmp_path / 'marker.txt').write_text('safe')
    with pytest.raises(FileExistsError, match='not empty'):
        run_predictor(FROZEN, tmp_path)
    assert (tmp_path / 'marker.txt').read_text() == 'safe'


def test_release_research_gate_blocked():
    q = json.loads((FROZEN / 'outputs' / '16_puerta_calidad.json').read_text())
    assert not q['can_publish']
    assert q['national_complete_monthly_exactly_constrained']
    assert q['geih_represented_national_monthly_not_forced']


def test_explicit_export_preserves_provenance_and_no_city_invention(tmp_path):
    report=export_experimental(FROZEN,tmp_path/'export')
    assert report['national_export_rows']==404*15
    assert report['represented_national_is_department_proxy_not_dane_official']
    assert (tmp_path/'export'/'sectorial_departamental_1993_2026_EXPERIMENTAL.csv').is_file()
    assert (tmp_path/'export'/'sectorial_nacional_1993_2026_EXPERIMENTAL.csv').is_file()
    assert not (tmp_path/'export'/'ciudades.csv').exists()
