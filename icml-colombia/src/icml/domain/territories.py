"""Territorial reference catalogs (departments and urban domains).

Catalogs are loaded from package data so that codes and names are never
hard-coded across modules.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from icml.domain._resources import read_reference_table

_TERRITORIES_FILE = "territories.csv"
_URBAN_DOMAINS_FILE = "urban_domains.csv"


class UrbanDomainKind(StrEnum):
    """Nature of an urban domain."""

    OBSERVED_CITY = "observed_city"
    SYNTHETIC_SIGNAL = "synthetic_signal"


@dataclass(frozen=True)
class Territory:
    """A departmental territory (32 departments plus Bogotá D.C.)."""

    dane_code: int
    name: str
    is_capital_district: bool


@dataclass(frozen=True)
class UrbanDomain:
    """An urban domain: a GEIH city/metro area or a synthetic signal."""

    dane_code: int
    name: str
    kind: UrbanDomainKind
    legacy_unit_type: str

    @property
    def is_synthetic(self) -> bool:
        """Return whether the domain is a modeling signal, not DANE data."""
        return self.kind is UrbanDomainKind.SYNTHETIC_SIGNAL


def _parse_bool(value: object) -> bool:
    text = str(value).strip().lower()
    if text not in {"true", "false"}:
        raise ValueError(f"Invalid boolean in reference table: {value!r}")
    return text == "true"


@cache
def load_territories() -> tuple[Territory, ...]:
    """Return the 33 departmental territories ordered by DANE code.

    Raises
    ------
    ValueError
        If the catalog contains duplicated codes.
    """
    table = read_reference_table(_TERRITORIES_FILE)
    territories = tuple(
        Territory(
            dane_code=int(row["dane_code"]),
            name=str(row["name"]),
            is_capital_district=_parse_bool(row["is_capital_district"]),
        )
        for row in table
    )
    _ensure_unique_codes(t.dane_code for t in territories)
    return tuple(sorted(territories, key=lambda t: t.dane_code))


@cache
def load_urban_domains() -> tuple[UrbanDomain, ...]:
    """Return the 33 urban domains (32 cities plus one synthetic signal).

    Raises
    ------
    ValueError
        If the catalog contains duplicated codes or unknown kinds.
    """
    table = read_reference_table(_URBAN_DOMAINS_FILE)
    domains = tuple(
        UrbanDomain(
            dane_code=int(row["dane_code"]),
            name=str(row["name"]),
            kind=UrbanDomainKind(row["kind"]),
            legacy_unit_type=str(row["legacy_unit_type"]),
        )
        for row in table
    )
    _ensure_unique_codes(d.dane_code for d in domains)
    return tuple(sorted(domains, key=lambda d: d.dane_code))


def territory_codes() -> tuple[int, ...]:
    """Return the DANE codes of the 33 territories."""
    return tuple(t.dane_code for t in load_territories())


def _ensure_unique_codes(codes: Iterable[int]) -> None:
    values = list(codes)
    duplicated = sorted({c for c in values if values.count(c) > 1})
    if duplicated:
        raise ValueError(f"Duplicated DANE codes in catalog: {duplicated}")
