import os
from pathlib import Path

import pytest

from icml.regression.catalog import GoldenCatalog, load_catalog

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPOSITORY_ROOT / "configs" / "golden" / "rc1_catalog.toml"
GOLDEN_ENV_VAR = "ICML_GOLDEN_DIR"
SOURCES_ENV_VAR = "ICML_SOURCES_ROOT"
# The core delivery keeps the operational sources next to the package.
DEFAULT_SOURCES_ROOT = REPOSITORY_ROOT


@pytest.fixture(scope="session")
def catalog() -> GoldenCatalog:
    return load_catalog(CATALOG_PATH)


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    value = os.environ.get(GOLDEN_ENV_VAR)
    if not value:
        pytest.skip(f"{GOLDEN_ENV_VAR} not set; golden tests skipped")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"{GOLDEN_ENV_VAR} does not point to a folder: {path}")
    return path


@pytest.fixture(scope="session")
def sources_root(golden_dir: Path) -> Path:
    """Root that holds the sources the ``configs/rc1`` TOML files name.

    The golden folder keeps the RC1 *legacy* layout (``fases/...``) used
    to read reference tables, whereas the configuration paths follow the
    core layout (``insumos/fuentes/...``). The two roots are therefore
    separate. Depending on ``golden_dir`` keeps the skip behaviour when
    no golden folder is configured.
    """
    value = os.environ.get(SOURCES_ENV_VAR)
    path = Path(value) if value else DEFAULT_SOURCES_ROOT
    if not (path / "datos").is_dir():
        pytest.fail(
            f"No 'datos' folder under the sources root {path}; set "
            f"{SOURCES_ENV_VAR} to the core delivery root."
        )
    return path

LOCK_FILE = REPOSITORY_ROOT / "requirements" / "lock-py312.txt"
# Packages whose versions change RC1 numbers beyond 1e-6 persons: the
# Chow-Lin rho is estimated by a numerical optimizer (scipy), so another
# scipy/numpy release converges to a slightly different rho.
NUMERICAL_PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "statsmodels",
    "tempdisagg",
    "scikit-learn",
    "xgboost",
)


def _locked_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for line in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        name, separator, version = line.strip().partition("==")
        if separator:
            versions[name.lower()] = version
    return versions


@pytest.fixture(scope="session", autouse=True)
def locked_numerical_environment() -> None:
    """Golden equivalence is only meaningful in the locked environment."""
    from importlib import metadata

    locked = _locked_versions()
    mismatches = {
        name: (metadata.version(name), locked[name])
        for name in NUMERICAL_PACKAGES
        if name in locked and metadata.version(name) != locked[name]
    }
    if mismatches and os.environ.get(GOLDEN_ENV_VAR):
        pytest.fail(
            "Golden tests require the locked numerical environment "
            f"(installed, locked): {mismatches}"
        )


CONFIGS = REPOSITORY_ROOT / "configs" / "rc1"


@pytest.fixture(scope="session")
def full_chain(sources_root, tmp_path_factory):
    """Run all six stages once from the RC1 sources (shared by tests)."""
    from icml.departmental.pipeline import (
        DepartmentalPipeline,
        load_departmental_config,
    )
    from icml.integration.pipeline import (
        IntegrationPipeline,
        load_integration_config,
    )
    from icml.io.artifacts import ArtifactStore
    from icml.modeling.pipeline import ModelingPipeline, load_modeling_config
    from icml.national.pipeline import NationalPipeline, load_national_config
    from icml.reconciliation.pipeline import (
        ReconciliationPipeline,
        load_reconciliation_config,
    )
    from icml.urban.pipeline import UrbanPipeline, load_urban_config

    root = tmp_path_factory.mktemp("full_chain")

    def store(name: str) -> ArtifactStore:
        return ArtifactStore(root / name)

    NationalPipeline(load_national_config(CONFIGS / "national.toml")).run(
        sources_root, store("national")
    )
    UrbanPipeline(load_urban_config(CONFIGS / "urban.toml")).run(
        sources_root, store("national"), store("urban")
    )
    DepartmentalPipeline(
        load_departmental_config(CONFIGS / "departmental.toml")
    ).run(sources_root, store("national"), store("departmental"))
    IntegrationPipeline(
        load_integration_config(CONFIGS / "integration.toml")
    ).run(
        sources_root,
        store("national"),
        store("urban"),
        store("departmental"),
        store("integration"),
    )
    modeling = ModelingPipeline(
        load_modeling_config(CONFIGS / "modeling.toml")
    ).run(store("integration"), store("departmental"), store("modeling"))
    reconciliation = ReconciliationPipeline(
        load_reconciliation_config(CONFIGS / "reconciliation.toml")
    ).run(
        store("modeling"),
        store("integration"),
        store("departmental"),
        store("reconciliation"),
    )
    return {
        "stores": {
            name: store(name)
            for name in (
                "national",
                "urban",
                "departmental",
                "integration",
                "modeling",
                "reconciliation",
            )
        },
        "modeling": modeling,
        "reconciliation": reconciliation,
    }
