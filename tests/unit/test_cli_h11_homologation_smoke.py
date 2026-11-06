"""H17 CLI smoke: H11 executes without importing the full labor pipeline."""
from pathlib import Path

from icml.cli import main


def test_cli_command_dispatch_without_unrelated_pipeline_import(tmp_path):
    root = Path(__file__).resolve().parents[2] / 'datos' / '2_procesamiento' / 'sectorial_h11'
    src = root / 'inputs'
    code = main([
        'sectoral', 'homologate-historical',
        '--dane-csv', str(src / 'dane_4_ramas_anuales_vintages.csv'),
        '--link-csv', str(src / 'h11_link_2001_07_FULL.csv'),
        '--totals-csv', str(src / 'totales_icml_1993_2001.csv'),
        '--mapping-csv', str(src / '11_crosswalk_ENH_4_grupos_a_15_ramas_CIIU4.csv'),
        '--output', str(tmp_path),
    ])
    assert code == 0
    assert (tmp_path/'11_retropolacion_1993_2001_HOMOLOGADA_EXPERIMENTAL.csv').is_file()
