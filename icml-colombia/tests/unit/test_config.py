from dataclasses import dataclass
from pathlib import Path

import pytest

from icml.config import (
    ConfigurationError,
    build_dataclass,
    load_toml,
    section,
)
from icml.national.pipeline import load_national_config

REPOSITORY = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Example:
    alpha: float
    beta: int = 1


def test_strict_keys():
    assert build_dataclass(Example, {"alpha": 1.0}, context="x").beta == 1
    with pytest.raises(ConfigurationError, match="unknown"):
        build_dataclass(Example, {"alpha": 1.0, "gamma": 2}, context="x")
    with pytest.raises(ConfigurationError, match="missing"):
        build_dataclass(Example, {}, context="x")


def test_missing_section_is_reported():
    with pytest.raises(ConfigurationError, match="a.b"):
        section({"a": {}}, "a.b")


def test_rc1_national_config_loads():
    config = load_national_config(REPOSITORY / "configs/rc1/national.toml")
    assert config.disaggregation.method == "chow-lin-maxlog"
    assert config.seasonality.strength == 0.5


def test_typo_in_config_is_an_error(tmp_path):
    text = (REPOSITORY / "configs/rc1/national.toml").read_text(
        encoding="utf-8"
    )
    broken = tmp_path / "national.toml"
    broken.write_text(
        text.replace("strength = 0.5", "strenght = 0.5"), encoding="utf-8"
    )
    with pytest.raises(ConfigurationError, match="strenght"):
        load_national_config(broken)
    assert load_toml(broken)["national"]["seasonality"]["strenght"] == 0.5
