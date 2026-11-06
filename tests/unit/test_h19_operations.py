"""Operational release gate: frozen integrity and safe next-month staging."""
import json
from pathlib import Path

import pandas as pd
import pytest

from icml.operations.monthly_staging import preflight, stage_update
from icml.pipeline.vintage import VintageError, VintagePolicy, with_revision_state

KEYS = ["dep_code", "period"]
QUANTITIES = ["employed", "unemployed", "labor_force", "inactive", "working_age"]
OLD = VintagePolicy("2026-08", 2025, 12)
NEW = VintagePolicy("2026-09", 2025, 12)


def _frames():
    months = list(pd.period_range("2025-09", "2026-08", freq="M").astype(str))
    previous = pd.DataFrame({"period": months, "dep_code": "05", "employed": 100.,
                             "unemployed": 20., "labor_force": 120., "inactive": 30.,
                             "working_age": 150., "status_label": "research"})
    old = with_revision_state(previous, OLD)
    next_row = previous.tail(1).copy()
    next_row["period"] = "2026-09"
    new = pd.concat([previous, next_row], ignore_index=True)
    return old, new


def _files(tmp_path, old=None, new=None):
    orig, cand = _frames()
    if old is not None:
        orig = old
    if new is not None:
        cand = new
    p, q = tmp_path / "old.csv", tmp_path / "new.csv"
    orig.to_csv(p, index=False)
    cand.to_csv(q, index=False)
    return p, q


def _stage(tmp_path, previous=None, candidate=None, out="staged"):
    p, q = _files(tmp_path, previous, candidate)
    return stage_update(p, q, tmp_path / out, KEYS, QUANTITIES, OLD, NEW)


def test_allowed_one_month_staged_and_input_immutable(tmp_path):
    p, q = _files(tmp_path)
    initial = p.read_bytes(), q.read_bytes()
    result = stage_update(p, q, tmp_path / "staged", KEYS, QUANTITIES, OLD, NEW)
    assert result["status"] == "ACCEPTED_STAGED_NOT_PUBLISHED"
    assert result["new_rows"] == 1
    assert result["protected_cells_changed"] == 0
    assert (p.read_bytes(), q.read_bytes()) == initial
    assert len(pd.read_csv(tmp_path / "staged/19_candidato_con_estados.csv")) == 13
    assert json.loads((tmp_path / "staged/19_actualizacion_auditoria.json").read_text())["canonical_published"] is False


def test_frozen_value_blocked_with_report(tmp_path):
    old, new = _frames()
    new.loc[new.period == "2025-09", "employed"] = 105.
    new.loc[new.period == "2025-09", "labor_force"] = 125.
    new.loc[new.period == "2025-09", "working_age"] = 155.
    result = _stage(tmp_path, old, new)
    assert result["status"] == "BLOCKED_FROZEN_HISTORY"
    assert not (tmp_path / "staged/19_candidato_con_estados.csv").exists()
    assert (tmp_path / "staged/19_cambios_por_celda.csv").exists()


def test_frozen_metadata_blocked(tmp_path):
    old, new = _frames()
    new.loc[new.period == "2025-09", "status_label"] = "rewritten"
    result = _stage(tmp_path, old, new)
    assert result["status"] == "BLOCKED_FROZEN_HISTORY"


def test_drop_history_rejected(tmp_path):
    old, new = _frames()
    new = new[new.period != "2025-10"]
    with pytest.raises(VintageError, match="non-contiguous|drops"):
        _stage(tmp_path, old, new)


def test_duplicate_keys_rejected(tmp_path):
    old, new = _frames()
    new = pd.concat([new, new.head(1)], ignore_index=True)
    with pytest.raises(VintageError, match="duplicate"):
        _stage(tmp_path, old, new)


def test_incorrect_previous_states_rejected(tmp_path):
    old, new = _frames()
    old.loc[old.period == "2025-09", "revision_state"] = "provisional"
    with pytest.raises(VintageError, match="does not match"):
        _stage(tmp_path, old, new)


def test_unbalanced_candidate_rejected(tmp_path):
    old, new = _frames()
    new.loc[new.period == "2026-09", "labor_force"] = 200
    with pytest.raises(VintageError, match="identity"):
        _stage(tmp_path, old, new)


def test_wrong_month_rejected(tmp_path):
    old, new = _frames()
    with pytest.raises(VintageError, match="exactly one month"):
        p, q = _files(tmp_path, old, new)
        stage_update(p, q, tmp_path / "wrong", KEYS, QUANTITIES, OLD,
                     VintagePolicy("2026-10", 2025, 12))


def test_do_not_overwrite_output(tmp_path):
    _stage(tmp_path)
    with pytest.raises(FileExistsError):
        p, q = tmp_path / "old.csv", tmp_path / "new.csv"
        stage_update(p, q, tmp_path / "staged", KEYS, QUANTITIES, OLD, NEW)


def test_preflight_rejects_hash_modified(tmp_path):
    root = tmp_path / "checkpoint"
    closure = root / "datos/2_procesamiento/productos_congelados"
    (closure / "sectorial").mkdir(parents=True)
    (root / "datos/2_procesamiento/sectorial_h16/outputs").mkdir(parents=True)
    name = "sectorial_departamental_1993_2026_EXPERIMENTAL.csv"
    source = root / "datos/2_procesamiento/sectorial_h16/outputs/16_matriz_mensual_1993_2026_EXPERIMENTAL.csv"
    export = closure / "sectorial" / name
    source.write_text("a,b\\n1,2\\n")
    export.write_text("different")
    (closure / "MANIFIESTO_CIERRE_SHA256.json").write_text(json.dumps({"files_sha256": {"sectorial/" + name: "bad_hash"}}))
    result = preflight(root, tmp_path / "report")
    assert result["status"] == "FAIL_INTEGRITY"
    assert result["h18_files_verified"] == 0
    assert result["golden"]["status"] == "NOT_EXECUTED_NO_EXTERNAL_REFERENCE"


def test_new_month_must_include_all_entities(tmp_path):
    old, new = _frames()
    previous_other = old.copy()
    previous_other["dep_code"] = "08"
    old = pd.concat([old, previous_other], ignore_index=True)
    next_other = new.copy()
    next_other["dep_code"] = "08"
    new = pd.concat([new, next_other[next_other.period.ne("2026-09")]], ignore_index=True)
    with pytest.raises(VintageError, match="missing or unexpected entities"):
        _stage(tmp_path, old, new)
