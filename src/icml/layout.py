"""Where things live in a project checkout.

Every path below is relative to the project root (the folder that holds
``datos/`` and ``pyproject.toml``). The data tree keeps its original
Spanish folder names on purpose: hundreds of versioned manifests, catalogs
and migration maps record those paths, and renaming them would break the
hash-based integrity checks that protect the frozen vintage.

Modules that read a single, operation-specific file keep that file name
next to the code that understands its schema; this module only defines
the shared anchors that several modules need to agree on.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------- data

#: Original DANE annexes and Excel workbooks (inputs that are never edited).
INGESTION_DIR = "datos/1_ingesta"
#: Prepared sources, frozen parameters, frozen products and the published base.
PROCESSING_DIR = "datos/2_procesamiento"
#: Timestamped deliveries, their simple files and their plots.
OUTPUT_DIR = "datos/3_salida"

#: The published base used by the next incremental update.
CURRENT_DIR = f"{PROCESSING_DIR}/vigente"
#: Scratch space of each recalculation (contents are not versioned).
RUNS_DIR = f"{PROCESSING_DIR}/_corridas"
#: Tables derived from the original workbooks, by stage.
PREPARED_SOURCES_DIR = f"{PROCESSING_DIR}/fuentes_preparadas"
#: Frozen stage parameters and closures that a recalculation reuses.
FROZEN_PARAMETERS_DIR = f"{PROCESSING_DIR}/parametros_congelados"
#: The eight frozen products of the reference vintage.
FROZEN_PRODUCTS_DIR = f"{PROCESSING_DIR}/productos_congelados"
#: Source inventories and lineage registers.
CATALOGS_DIR = f"{PROCESSING_DIR}/catalogos"
#: Canonical source catalog with the hash of every stage input.
SOURCE_CATALOG = f"{CATALOGS_DIR}/catalogo_fuentes.json"

# --------------------------------------------------------------------- code

#: Stage configurations of the reference vintage (RC1).
CONFIGS_DIR = "configs/rc1"
#: Catalog of the RC1 golden reference artifacts.
GOLDEN_CATALOG = "configs/golden/rc1_catalog.toml"
#: Pinned runtime used by the certification audit.
LOCK_FILE = "requirements/lock-py312.txt"

#: Folder suffixes of the two companions of a delivery. They are part of the
#: published layout, so they are not translated.
SIMPLE_SUFFIX = "_sencillo"
PLOTS_SUFFIX = "_graficos"


def package_root() -> Path:
    """The project root as seen from the installed package (``src/icml``)."""
    return Path(__file__).resolve().parents[2]


def find_project_root(given: Path | None = None) -> Path:
    """The project root: ``given``, else the current folder or the closest one above it.

    Raises
    ------
    FileNotFoundError
        When no candidate holds both ``datos/1_ingesta`` and ``pyproject.toml``.
    """
    candidates = [Path(given)] if given else [Path.cwd(), *Path.cwd().parents]
    for folder in candidates:
        folder = folder.resolve()
        if (folder / INGESTION_DIR).is_dir() and (folder / "pyproject.toml").is_file():
            return folder
    raise FileNotFoundError(
        "Project folder not found (the one that holds datos/ and pyproject.toml). "
        "Run the command inside it or pass --root."
    )
