import json

import pandas as pd
import pytest

from icml.io.artifacts import ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_bytes, sha256_file
from icml.io.tables import read_table, write_table
from icml.pipeline.manifest import RunManifest, validate_run_id


@pytest.fixture
def frame():
    return pd.DataFrame(
        {"periodo": ["2000-01", "2000-02"], "employed": [1.0 / 3, 2.5]}
    )


def test_write_is_deterministic_and_round_trips(tmp_path, frame):
    first = write_table(frame, tmp_path / "a.csv")
    second = write_table(frame, tmp_path / "b.csv")
    assert sha256_file(first) == sha256_file(second)
    restored = read_table(first)
    assert restored["employed"].tolist() == frame["employed"].tolist()


def test_write_refuses_overwrite(tmp_path, frame):
    path = write_table(frame, tmp_path / "a.csv")
    with pytest.raises(FileExistsError):
        write_table(frame, path)
    write_table(frame, path, overwrite=True)


def test_write_leaves_no_temporary_files(tmp_path, frame):
    write_table(frame, tmp_path / "a.csv")
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]


def test_read_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_table(tmp_path / "missing.csv")


def test_sha256_helpers_agree(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"icml")
    assert sha256_file(path) == sha256_bytes(b"icml")


@pytest.mark.parametrize(
    ("artifact_id", "relative_path"),
    [
        ("Bad", "a.csv"),
        ("national", "a.csv"),
        ("a.b", "../a.csv"),
        ("a.b", "/abs.csv"),
    ],
)
def test_invalid_specs_rejected(artifact_id, relative_path):
    with pytest.raises(ValueError):
        ArtifactSpec(artifact_id, relative_path)


def test_store_records_written_and_read_artifacts(tmp_path, frame):
    store = ArtifactStore(tmp_path)
    spec = ArtifactSpec(
        "national.monthly", "national/monthly.csv", keys=("periodo",)
    )
    written = store.write(spec, frame)
    assert written.n_rows == 2
    reread = ArtifactStore(tmp_path).read(spec)
    assert reread.shape == frame.shape
    assert store.records[0].sha256 == written.sha256


def test_store_rejects_duplicated_keys(tmp_path, frame):
    store = ArtifactStore(tmp_path)
    spec = ArtifactSpec("national.monthly", "m.csv", keys=("periodo",))
    with pytest.raises(ValueError, match="duplicated"):
        store.write(spec, pd.concat([frame, frame]))


def test_store_rejects_missing_keys(tmp_path, frame):
    spec = ArtifactSpec("national.monthly", "m.csv", keys=("dep_code",))
    with pytest.raises(ValueError, match="missing key"):
        ArtifactStore(tmp_path).write(spec, frame)


def test_store_artifacts_are_immutable(tmp_path, frame):
    store = ArtifactStore(tmp_path)
    spec = ArtifactSpec("national.monthly", "m.csv")
    store.write(spec, frame)
    with pytest.raises(FileExistsError):
        store.write(spec, frame)


def test_manifest_serialization_and_immutability(tmp_path, frame):
    store = ArtifactStore(tmp_path)
    record = store.write(ArtifactSpec("national.monthly", "m.csv"), frame)
    manifest = RunManifest(
        run_id="run_001",
        stage="test",
        config_sha256="0" * 64,
        inputs=(),
        outputs=(record,),
    )
    path = manifest.write(tmp_path / "manifest.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["outputs"][0]["sha256"] == record.sha256
    assert "pandas" in payload["environment"]
    with pytest.raises(FileExistsError):
        manifest.write(path)


@pytest.mark.parametrize("run_id", ["", "-x", "a b", "a/b", "x" * 81])
def test_invalid_run_ids(run_id):
    with pytest.raises(ValueError):
        validate_run_id(run_id)
