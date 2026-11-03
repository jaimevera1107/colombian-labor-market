"""Typed loading of TOML configuration into frozen dataclasses.

Every statistical parameter lives in a versioned TOML file. Sections are
mapped onto dataclasses with strict checking: unknown or missing keys are
errors, so a typo can never silently fall back to a default.
"""

from __future__ import annotations

import dataclasses
import hashlib
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class ConfigurationError(ValueError):
    """Raised when a configuration file does not match its schema."""


def load_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def config_sha256(path: Path) -> str:
    """Return the SHA-256 of a configuration file (for run manifests)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(payload: Mapping[str, Any], dotted_name: str) -> Mapping[str, Any]:
    """Return a nested section such as ``"national.splice"``.

    Raises
    ------
    ConfigurationError
        If the section is missing or is not a table.
    """
    current: Any = payload
    for part in dotted_name.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ConfigurationError(
                f"Missing configuration section: [{dotted_name}]"
            )
        current = current[part]
    if not isinstance(current, Mapping):
        raise ConfigurationError(f"[{dotted_name}] is not a table")
    return current


def build_dataclass(
    cls: type[T], values: Mapping[str, Any], *, context: str
) -> T:
    """Instantiate a dataclass from a mapping with strict key checking.

    Parameters
    ----------
    cls : type
        Target dataclass.
    values : Mapping[str, Any]
        Raw values (e.g. a TOML section).
    context : str
        Section name used in error messages.

    Raises
    ------
    ConfigurationError
        If keys are missing or unknown, or the dataclass rejects a value.
    """
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")
    fields = {f.name: f for f in dataclasses.fields(cls) if f.init}
    required = {
        name
        for name, f in fields.items()
        if f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING
    }
    unknown = sorted(set(values) - set(fields))
    missing = sorted(required - set(values))
    if unknown or missing:
        raise ConfigurationError(
            f"[{context}] unknown keys {unknown}, missing keys {missing}"
        )
    try:
        return cls(**dict(values))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"[{context}] {exc}") from exc
