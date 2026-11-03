"""The transfer evaluation never sees the hidden department's data.

Leakage test: multiplying every label and official anchor of the hidden
department by 1.5 must leave its estimates unchanged, so each level error
must move exactly as ``(1 + e) / 1.5 - 1``.
"""

import shutil

import numpy as np
import pandas as pd
import pytest

from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.evaluation.pipeline import OUTPUTS, TransferEvaluationPipeline
from icml.io.artifacts import ArtifactStore

from .conftest import CONFIGS

pytestmark = pytest.mark.golden

HIDDEN = 68
FACTOR = 1.5
LEVELS = ("employed", "unemployed", "inactive", "labor_force", "working_age")


def _config(tmp_path):
    text = (CONFIGS / "evaluation.toml").read_text(encoding="utf-8")
    text = text.replace("hidden_codes = []", f"hidden_codes = [{HIDDEN}]")
    text = text.replace(
        'candidates = ["xgb_ward", "hybrid", "xgb_none", "urban_analog", '
        '"national_rates"]',
        'candidates = ["xgb_ward", "urban_analog"]',
    )
    for name in ("modeling", "reconciliation"):
        text = text.replace(
            f'"{name}.toml"', f'"{(CONFIGS / f"{name}.toml").as_posix()}"'
        )
    path = tmp_path / "evaluation.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _perturbed_departmental(source, target):
    shutil.copytree(source.root, target)
    for key, columns in (
        ("official_anchors", (*LEVELS, "population")),
        ("monthly_revised", (*LEVELS, "population")),
    ):
        path = target / DEPARTMENTAL_OUTPUTS[key].relative_path
        table = pd.read_csv(path)
        rows = table["dep_code"] == HIDDEN
        for column in columns:
            table.loc[rows, column] = table.loc[rows, column] * FACTOR
        table.to_csv(path, index=False)
    return ArtifactStore(target)


def test_hidden_department_does_not_leak(full_chain, tmp_path):
    config = _config(tmp_path)
    stores = full_chain["stores"]
    baseline = TransferEvaluationPipeline(config).run(
        stores["integration"],
        stores["departmental"],
        ArtifactStore(tmp_path / "baseline"),
    )
    perturbed_store = _perturbed_departmental(
        stores["departmental"], tmp_path / "departmental"
    )
    TransferEvaluationPipeline(config).run(
        stores["integration"],
        perturbed_store,
        ArtifactStore(tmp_path / "perturbed"),
    )
    assert baseline.diagnostics["hidden"] == [HIDDEN]
    keys = ["hidden_code", "candidate", "stage", "year"]
    first = (
        ArtifactStore(tmp_path / "baseline")
        .read(OUTPUTS["transfer_annual"])
        .set_index(keys)
        .sort_index()
    )
    second = (
        ArtifactStore(tmp_path / "perturbed")
        .read(OUTPUTS["transfer_annual"])
        .set_index(keys)
        .sort_index()
    )
    for level in (*LEVELS, "population"):
        column = f"{level}_pct_error"
        expected = (1 + first[column] / 100) / FACTOR - 1
        np.testing.assert_allclose(
            second[column] / 100, expected, rtol=0, atol=1e-9
        )
    for rate in ("unemployment_rate", "employment_rate", "participation_rate"):
        column = f"{rate}_pp_error"
        np.testing.assert_allclose(second[column], first[column], atol=1e-7)
