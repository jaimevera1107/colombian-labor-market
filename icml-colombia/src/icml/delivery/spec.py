"""Declarative specification of how each product splits by universe.

Two universes are delivered for every product:

* ``censo``: the complete territory (CNPV 2018 population, ``ICML_COMPLETO``).
* ``geih``: the part of the territory that the GEIH represents.

The internal products encode that split in three different ways (extra
columns, extra rows, or suffixed columns). This module states, for each
original column, where it goes, so that the split is lossless and
auditable: ``tests/unit/test_delivery.py`` checks that every original
column is assigned exactly once.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from icml.domain.cutoff import N_MONTHS, ROWS_33, ROWS_NATIONAL

UNIVERSES: tuple[str, str] = ("censo", "geih")
DOMAINS: tuple[str, ...] = ("laboral", "informalidad", "sectorial")
LEVELS: tuple[str, ...] = ("nacional", "ciudades", "departamentos")

#: Columns that identify a territory or a period; kept as text in Excel.
TEXT_COLUMNS: frozenset[str] = frozenset(
    {
        "period",
        "dep_code",
        "city_code",
        "sector_code",
        "territory_id",
        "territory_name",
        "city_name",
        "national_type",
    }
)


@dataclass(frozen=True)
class ProductSpec:
    """How one internal product is split into the two universes.

    Attributes
    ----------
    product_id : str
        Identifier of the internal product (``labor.departamentos``).
    domain : str
        Delivered domain: ``laboral``, ``informalidad`` or ``sectorial``.
    level : str
        Territorial level: ``nacional``, ``ciudades`` or ``departamentos``.
    split : str
        ``rows`` (one universe per row value), ``columns`` (one universe per
        group of columns) or ``shared`` (same series in both universes).
    expected_rows : int
        Rows of the *internal* product (not of each delivered file).
    row_column : str
        For ``rows``: the column that carries the universe.
    row_values : Mapping[str, str]
        For ``rows``: universe -> value of ``row_column``.
    keys : tuple[str, ...]
        For ``columns``: identifying columns copied to both universes.
    census, geih : Mapping[str, str]
        For ``columns``: original column -> delivered column.
    both : tuple[str, ...]
        For ``columns``: metadata columns copied to both universes.
    note : str
        Free text recorded in the manifest.
    """

    product_id: str
    domain: str
    level: str
    split: str
    expected_rows: int
    row_column: str = ""
    row_values: Mapping[str, str] = field(default_factory=dict)
    keys: tuple[str, ...] = ()
    census: Mapping[str, str] = field(default_factory=dict)
    geih: Mapping[str, str] = field(default_factory=dict)
    both: tuple[str, ...] = ()
    note: str = ""

    def assigned_columns(self) -> list[str]:
        """Return every original column the spec accounts for."""
        if self.split != "columns":
            return []
        return [*self.keys, *self.census, *self.geih, *self.both]


def _same(*names: str) -> dict[str, str]:
    """Map each name to itself."""
    return {name: name for name in names}


_LABOR_COUNTS = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
)
_CITIES_NOTE = (
    "Urban domains are GEIH domains and non-additive signals; no separate "
    "census-universe city series exists, so the same series is delivered "
    "in both universes."
)

SPECS: tuple[ProductSpec, ...] = (
    ProductSpec(
        "labor.nacionales",
        "laboral",
        "nacional",
        "rows",
        ROWS_NATIONAL,
        row_column="national_type",
        row_values={"censo": "ICML_COMPLETO", "geih": "DANE_REFERENCIA"},
        note=(
            "GEIH universe = national figure published by DANE. Columns "
            "represented_sum_* and gap_published_minus_sum_* compare it with "
            "the sum of the represented departments."
        ),
    ),
    ProductSpec(
        "labor.departamentos",
        "laboral",
        "departamentos",
        "columns",
        ROWS_33,
        keys=(
            "period",
            "year",
            "dep_code",
            "territory_id",
            "territory_name",
            "territory_level",
            "is_additive_member",
        ),
        census={
            **_same(
                *_LABOR_COUNTS,
                "unemployment_rate",
                "employment_rate",
                "participation_rate",
            ),
        },
        geih={
            "employed_represented": "employed",
            "unemployed_represented": "unemployed",
            "inactive_represented": "inactive",
            "labor_force_represented": "labor_force",
            "working_age_represented": "working_age",
            "population_represented": "population",
            **_same(
                "factor_employed",
                "factor_unemployed",
                "factor_inactive",
                "factor_labor_force",
                "factor_working_age",
                "factor_population",
                "factor_reference_status",
                "factor_is_assumed",
                "factor_employed_demographic",
                "factor_unemployed_demographic",
                "factor_inactive_demographic",
                "factor_labor_force_demographic",
                "factor_working_age_demographic",
                "factor_population_demographic",
                "employed_residual_share",
                "unemployed_residual_share",
                "inactive_residual_share",
                "population_residual_share",
            ),
        },
        both=("source",),
        note=(
            "GEIH rates are derived from the represented counts with the "
            "same identities as the census rates."
        ),
    ),
    ProductSpec(
        "labor.ciudades",
        "laboral",
        "ciudades",
        "shared",
        ROWS_33,
        note=_CITIES_NOTE,
    ),
    ProductSpec(
        "informalidad.nacionales",
        "informalidad",
        "nacional",
        "rows",
        ROWS_NATIONAL,
        row_column="national_type",
        row_values={"censo": "ICML_COMPLETO", "geih": "GEIH_REPRESENTADO_CNPV2018"},
    ),
    ProductSpec(
        "informalidad.departamentos",
        "informalidad",
        "departamentos",
        "columns",
        ROWS_33,
        keys=("period", "dep_code"),
        census={
            **_same(
                "geographic_employed",
                "population",
                "working_age",
                "labor_force",
                "employed",
                "unemployed",
                "inactive",
                "informality_rate",
                "outside_geih_population",
                "outside_geih_working_age",
                "outside_geih_labor_force",
                "outside_geih_employed",
                "outside_geih_unemployed",
                "outside_geih_inactive",
                "outside_geih_informal",
                "outside_geih_formal",
                "informality_complement_rate_assumed_equal",
            ),
            "informal_full": "informal",
            "formal_full": "formal",
        },
        geih={
            "geih_population": "population",
            "geih_working_age": "working_age",
            "geih_labor_force": "labor_force",
            "geih_employed": "employed",
            "geih_unemployed": "unemployed",
            "geih_inactive": "inactive",
            "informal_geih": "informal",
            "formal_geih": "formal",
            "geih_rate_derived": "informality_rate",
            **_same(
                "geih_domain_status",
                "factor_geih_population",
                "factor_geih_working_age",
                "factor_geih_labor_force",
                "factor_geih_employed",
                "factor_geih_unemployed",
                "factor_geih_inactive",
            ),
        },
        both=(
            "prior_rate",
            "prior_provenance",
            "national_employed",
            "national_target_rate",
            "provenance",
            "uncertainty_class",
            "is_official_monthly_rate",
            "estimation_status",
            "universe_modelled",
        ),
    ),
    ProductSpec(
        "informalidad.ciudades",
        "informalidad",
        "ciudades",
        "shared",
        ROWS_33,
        note=_CITIES_NOTE,
    ),
    ProductSpec(
        "sectorial.nacional",
        "sectorial",
        "nacional",
        "columns",
        N_MONTHS * 15,
        keys=("period", "sector_code"),
        census={"occupied_full": "occupied", "share_full": "share"},
        geih={
            "occupied_represented_department_proxy": "occupied",
            "share_represented_department_proxy": "share",
        },
        both=("source_status", "publication_status"),
        note="Experimental product; the represented series is a proxy.",
    ),
    ProductSpec(
        "sectorial.departamental",
        "sectorial",
        "departamentos",
        "columns",
        ROWS_33 * 15,
        keys=("period", "dep_code", "sector_code"),
        census={"employed_full_sector": "employed_sector", "sector_share": "sector_share"},
        geih={"employed_represented_sector_proxy": "employed_sector"},
        both=(
            "territorial_prior_status",
            "national_source_status",
            "annual_anchor_status",
        ),
        note=(
            "Experimental product; the represented series is a proxy. The "
            "GEIH sector_share is derived from it within each department "
            "and month."
        ),
    ),
)

SPECS_BY_ID: dict[str, ProductSpec] = {s.product_id: s for s in SPECS}
