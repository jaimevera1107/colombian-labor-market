"""H36 data regression: two official source months and prior-vintage consistency.

These are ground-truth source checks, NOT a scientific or publication gate.
"""
from pathlib import Path

from icml.operations.h22 import inspect_annex
from icml.operations.h35_social_annex import inspect_social_annex

ROOT = Path(__file__).resolve().parents[3]
from tests.annexes import annex


def test_july_and_august_source_contents_are_usable():
    for month, geih, social in (
        ('2026-07', annex('mercado_laboral', '2026-07'), annex('informalidad', '2026-07')),
        ('2026-08', annex('mercado_laboral', '2026-08'), annex('informalidad', '2026-08')),
    ):
        observations = inspect_annex(geih, [month])
        assert len(observations) == 2
        assert {r['domain'] for r in observations} == {'DANE_NACIONAL','DANE_13_CIUDADES'}
        audit = inspect_social_annex(social, month)
        assert audit['status'] == 'PASS_SOURCE_CONTENT'
        assert audit['social_security_rolling']['occupied_thousands'] > 0
        assert len(audit['observations']) == 5


def test_july_source_revision_absent_in_august_geih_annex():
    july = inspect_annex(annex('mercado_laboral', '2026-07'),['2026-07'])
    july_as_in_august = inspect_annex(annex('mercado_laboral', '2026-08'),['2026-07'])
    for old,new in zip(july,july_as_in_august,strict=True):
        assert old['domain'] == new['domain']
        assert old == new
