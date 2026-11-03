"""H27: authentic legacy data references; NOT numerical RC1 equivalence."""
import os
from pathlib import Path

import pytest

from icml.regression.catalog import load_catalog
from icml.regression.golden import check_integrity

ROOT = Path(__file__).resolve().parents[3]
# The RC1 references travel as a separate release (``legacy/`` is not versioned);
# ICML_GOLDEN_DIR points at them when they live elsewhere.
REFERENCES = Path(os.environ.get("ICML_GOLDEN_DIR") or ROOT / "legacy/validacion/rc1_original")
pytestmark = pytest.mark.skipif(not REFERENCES.is_dir(), reason="RC1 references not present (separate release)")


def test_all_102_original_rc1_reference_hashes_are_intact():
    catalog = load_catalog(ROOT / "icml-colombia/configs/golden/rc1_catalog.toml")
    assert len(catalog.artifacts) == 102
    assert check_integrity(REFERENCES, catalog) == ()


def test_old_code_is_not_included_in_recovered_reference_data():
    directory = REFERENCES
    assert directory.is_dir()
    assert not any(p.suffix in {".py", ".pyc", ".ipynb"} for p in directory.rglob("*"))
